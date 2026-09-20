"""Development-only closure integration: three PR24 sources and five controls.

No Run27 corpus, external target or new holdout is evaluated. Timings include
source bridge, search and built-in checking, recorded separately from proof
results. Replay checks proofs/explanations and stored outputs, without search
or Java. Finite checked-cell evaluation below is a validation oracle, not the
new standalone row executor planned for PR30.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

from research.observations.model import integer, require
from research.signed_bridge.cli import load
from research.signed_bridge.experiment import CASES, save, sha
from research.signed_bridge.model import request
from research.signed_predicates.frontend import select
from research.signed_predicates.semantics import evaluate
from .checker import check, rebuild
from .explain import explain

ROOT = Path(__file__).resolve().parents[2]
CONSTRUCTED = (("delayed16", "x == 16"), ("delayed256", "x == 256"),
               ("constant", "true"), ("sign", "x < 0"),
               ("unsigned_variant", "(x & (x - 1)) == 0"))


def cases(inputs):
    corpus = load(ROOT / "research/external/frozen_v2/CORPUS.json")
    for name, source_id, class_name, typ, width in CASES:
        raw = (inputs / (source_id + ".java")).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        require(blob == corpus["sources"][source_id]["blob"], "retained PR24 source identity")
        yield name, raw.decode("utf-8"), request({"class": class_name, "method": "isPowerOfTwo"}, typ), width
    for name, expression in CONSTRUCTED:
        text = "class Demo { public static boolean f(long x) { return " + expression + "; } }"
        yield name, text, request({"class": "Demo", "method": "f"}, "long"), None


def _evaluator(model, proof):
    edges = {(row["state"], row["symbol"]): row["next"] for row in proof["cells"]}
    def value(x, width):
        state = proof["initial"]
        for i in range(width):
            state = edges[state, str((x >> i) & 1)]
        return model.terminal[proof["blocks"][state][0]] == "true"
    return value


def run(inputs, output, *, replay=False):
    inputs, output = Path(inputs), Path(output)
    if replay:
        manifest = load(output / "MANIFEST.json")
        files = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
        require(set(manifest) == files - {"MANIFEST.json"}, "exact experiment file set")
        for path, expected in manifest.items():
            require(sha((output / path).read_bytes()) == expected, "modified artifact: " + path)
    else:
        require(not output.exists(), "fresh experiment needs a new directory")
        output.mkdir(parents=True)
    results, timings = {}, {}
    for name, text, selection, width in cases(inputs):
        directory = output / name
        if replay:
            certificate = load(directory / "certificate.json")
            require((directory / "source.java").read_text(encoding="utf-8") == text
                    and load(directory / "request.json") == selection, "case source/request identity")
        else:
            from .producer import derive
            start = time.perf_counter()
            certificate, produced = derive(text, selection)
            timings[name] = {"discovery_seconds": time.perf_counter() - start,
                             "includes": "bridge construction, observation search and built-in checking"}
            require(certificate is not None, "development discovery exhausted")
            directory.mkdir()
            (directory / "source.java").write_text(text, encoding="utf-8")
            save(directory / "request.json", selection)
            save(directory / "certificate.json", certificate)
            save(directory / "discovery.json", produced["discovery"])
        start = time.perf_counter()
        result = check(text, selection, certificate)
        explanation = explain(text, selection, certificate)
        if not replay:
            timings[name]["check_and_explain_seconds"] = time.perf_counter() - start
        ir, model, _ = rebuild(text, selection, certificate)
        value = _evaluator(model, certificate["observations"])
        native_count, small_count = 0, 0
        if width is not None:
            if replay:
                record = load(directory / "native.json")
            else:
                from research.signed_predicates.experiment import native, population
                xs = population(width)
                _, _, _, declaration, _ = select(text, selection["entry"], word_type=selection["word_type"])
                start = time.perf_counter()
                ys = native(declaration, selection["entry"]["method"], selection["word_type"], width, xs)
                timings[name]["native_seconds"] = time.perf_counter() - start
                record = {"width": width, "inputs": xs, "outputs": ys,
                          "source_sha256": ir["source_sha256"], "declaration_sha256": ir["declaration_sha256"],
                          "harness_sha256": sha((ROOT / "research/signed_predicates/experiment.py").read_bytes())}
                save(directory / "native.json", record)
            require(record["width"] == width and record["source_sha256"] == ir["source_sha256"]
                    and record["declaration_sha256"] == ir["declaration_sha256"]
                    and record["harness_sha256"] == sha((ROOT / "research/signed_predicates/experiment.py").read_bytes()),
                    "native source and harness binding")
            xs, ys = record["inputs"], record["outputs"]
            require(type(xs) is list and type(ys) is list and xs == sorted(set(xs))
                    and len(xs) == len(ys) and len(xs) == (69711 if width == 32 else 69839)
                    and all(integer(x, 0, (1 << width) - 1) for x in xs)
                    and all(type(y) is bool for y in ys), "native population shape")
            for x, y in zip(xs, ys):
                require(y == evaluate(ir, x, width) == value(x, width), "Java/IR/factor mismatch")
            native_count = len(xs)
        else:
            for w in range(1, 9):
                for x in range(1 << w):
                    require(evaluate(ir, x, w) == value(x, w), "constructed source/factor mismatch")
                    small_count += 1
        if replay:
            require(load(directory / "result.json") == result, "checked result changed")
            require(load(directory / "explanation.json") == explanation, "checked explanation changed")
        else:
            save(directory / "result.json", result)
            save(directory / "explanation.json", explanation)
        results[name] = {"status": result["status"], "model_states": result["model_states"],
                         "classes": result["classes"], "positive_classes": result["positive_classes"],
                         "questions": result["derived_observations"], "max_separator_length": result["max_witness_length"],
                         "separating_pairs": result["separating_class_pairs"],
                         "certificate_sha256": sha((directory / "certificate.json").read_bytes()),
                         "native_inputs": native_count, "constructed_word_checks": small_count}
    summary = {"schema": "qkf-signed-observation-development-v1", "cases": results,
               "counts": {"source_observation_verified": len(results)},
               "native_inputs": sum(r["native_inputs"] for r in results.values()),
               "constructed_word_checks": sum(r["constructed_word_checks"] for r in results.values()),
               "mismatches": 0, "target_checked": False, "new_holdout": False,
               "scope": "three retained PR24 methods plus five constructed sources; not Run27 or target coverage"}
    if replay:
        require(load(output / "SUMMARY.json") == summary, "summary recomputation")
    else:
        save(output / "SUMMARY.json", summary)
        save(output / "PERFORMANCE.json", timings)
        save(output / "MANIFEST.json", {p.relative_to(output).as_posix(): sha(p.read_bytes())
                                      for p in sorted(output.rglob("*")) if p.is_file()})
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(run(args.inputs, args.output, replay=args.replay), sort_keys=True))


if __name__ == "__main__":
    main()
