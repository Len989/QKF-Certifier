"""Row-runtime audit of the eight PR29 development packages, not a holdout.

First replay the unchanged upstream experiment. Then load each complete package
once and compare row-only execution with independently retained native/IR values
and the checked forward-cell oracle. No producer or Java is invoked here, even
in the first run. Upstream generation/native cost and loader/hot execution cost
are deliberately separate. Replay reads timing records but does not recreate them.
"""
import argparse
import json
from pathlib import Path
import time

from research.signed_bridge.cli import load as read_json
from research.signed_bridge.experiment import save, sha
from research.signed_observations.experiment import run as replay_previous, cases
from research.signed_predicates.frontend import read_source
from research.signed_predicates.semantics import evaluate
from .core import integer, require
from .runtime import load


def _direct(certificate):
    """Forward-cell control only; never used by the public runtime."""
    p = certificate["observations"]
    model = certificate["source_model"]["model"]
    cells = {(r["state"], r["symbol"]): r["next"] for r in p["cells"]}
    terminals = [model["terminal"][b[0]] for b in p["blocks"]]
    def value(x, width):
        require(integer(width, 1, 4096) and integer(x, 0, (1 << width) - 1), "direct control word")
        state = p["initial"]
        for i in range(width):
            state = cells[state, str((x >> i) & 1)]
        return terminals[state] == "true"
    return value


def run(inputs, prior, output, *, replay=False):
    inputs, prior, output = Path(inputs), Path(prior), Path(output)
    previous = replay_previous(inputs, prior, replay=True)
    require(previous["counts"] == {"source_observation_verified": 8}
            and previous["native_inputs"] == 209389 and not previous["target_checked"],
            "fixed PR29 development scope")
    if replay:
        manifest = read_json(output / "MANIFEST.json")
        files = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
        require(set(manifest) == files - {"MANIFEST.json"}, "exact runtime experiment file set")
        for name, expected in manifest.items():
            require(sha((output / name).read_bytes()) == expected, "changed runtime artifact: " + name)
    else:
        require(not output.exists(), "new runtime output directory required")
        output.mkdir(parents=True)
    results, timings = {}, {}
    for name, text, selection, native_width in cases(inputs):
        directory = output / name
        certificate = read_json(prior / name / "certificate.json")
        start = time.perf_counter()
        runner, receipt = load(text, selection, certificate)
        load_time = time.perf_counter() - start
        direct = _direct(certificate)
        if native_width is None:
            ir = read_source(text, selection["entry"], selection["word_type"])
            population = [(x, w, evaluate(ir, x, w)) for w in range(1, 9) for x in range(1 << w)]
        else:
            native = read_json(prior / name / "native.json")
            population = [(x, native_width, y) for x, y in zip(native["inputs"], native["outputs"])]
        start = time.perf_counter()
        for x, width, expected in population:
            require(runner.value(x, width) == expected == direct(x, width), "runtime/IR/native/control mismatch")
        compare_time = time.perf_counter() - start
        # Wide inputs are mathematical specializations, never additional Java runs.
        wide_checks = 0
        for width in (1, 32, 64, 128, 256, 4096):
            for raw in sorted({0, 1, (1 << (width - 1)), (1 << width) - 1}):
                require(runner.value(raw, width) == direct(raw, width), "wide row/control disagreement")
                wide_checks += 1
        result = {"status": receipt["status"], "classes": receipt["classes"],
                  "positive_classes": receipt["positive_classes"],
                  "stored_atom_images": receipt["stored_atom_images"],
                  "row_templates": receipt["row_templates"],
                  "certificate_sha256": sha((prior / name / "certificate.json").read_bytes()),
                  "action_sha256": receipt["action_sha256"],
                  "native_record_checks": len(population) if native_width else 0,
                  "constructed_word_checks": 0 if native_width else len(population),
                  "wide_control_checks": wide_checks,
                  "target_checked": False, "lean_checked": False, "mismatches": 0}
        if replay:
            require(read_json(directory / "receipt.json") == receipt, "load receipt changed")
            require(read_json(directory / "runtime-view.json") == runner.describe(), "runtime view changed")
            require(read_json(directory / "result.json") == result, "runtime result changed")
        else:
            directory.mkdir()
            save(directory / "receipt.json", receipt)
            save(directory / "runtime-view.json", runner.describe())
            save(directory / "result.json", result)
            # A deliberately bounded warm API comparison on identical inputs.
            # No claim of a general speedup; row scanning may be slower.
            width = native_width or 64
            xs = tuple(range(2048))
            warm = {}
            for label, evaluator in (("atomic_rows", runner.value), ("forward_cells_control", direct)):
                samples = []
                for _ in range(3):
                    start = time.perf_counter()
                    checksum = sum(evaluator(x, width) for x in xs)
                    samples.append(time.perf_counter() - start)
                warm[label] = {"seconds": samples, "checksum": checksum}
            require(warm["atomic_rows"]["checksum"] == warm["forward_cells_control"]["checksum"],
                    "warm benchmark control mismatch")
            timings[name] = {"checked_load_seconds": load_time,
                             "runtime_and_direct_comparison_seconds": compare_time,
                             "warm": warm, "warm_inputs_per_repeat": len(xs),
                             "warm_width": width, "warm_repeats": 3}
        results[name] = result
    summary = {"schema": "qkf-signed-row-runtime-development-v1", "cases": results,
               "counts": {"source_runtime_verified": len(results)},
               "native_record_checks": sum(r["native_record_checks"] for r in results.values()),
               "constructed_word_checks": sum(r["constructed_word_checks"] for r in results.values()),
               "wide_control_checks": sum(r["wide_control_checks"] for r in results.values()),
               "upstream_summary_sha256": sha((prior / "SUMMARY.json").read_bytes()),
               "mismatches": 0, "target_checked": False, "lean_checked": False, "new_holdout": False,
               "scope": "eight PR29 development interfaces; native outputs audited, not rerun by this module"}
    if replay:
        require(read_json(output / "SUMMARY.json") == summary, "runtime summary recomputation")
    else:
        save(output / "SUMMARY.json", summary)
        save(output / "PERFORMANCE.json", {"cases": timings,
             "upstream_generation_cost": read_json(prior / "PERFORMANCE.json"),
             "notes": "upstream discovery/native costs separate; warm times exclude loading; no SMT comparison"})
        save(output / "MANIFEST.json", {p.relative_to(output).as_posix(): sha(p.read_bytes())
                                       for p in sorted(output.rglob("*")) if p.is_file()})
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("prior", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(run(args.inputs, args.prior, args.output, replay=args.replay), sort_keys=True))


if __name__ == "__main__":
    main()
