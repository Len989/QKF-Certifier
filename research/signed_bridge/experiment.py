"""Development-only source-model correspondence on three retained PR24 methods.

No new holdout, property goal or observation synthesis is performed. Replay
checks source-model proofs and audits saved native outputs; it does not run Java.
"""
import argparse
import hashlib
import json
from pathlib import Path

from research.observations.model import require
from research.signed_predicates.frontend import select
from research.signed_predicates.semantics import evaluate
from .checker import check, rebuild
from .cli import load
from .model import request, word_value

ROOT = Path(__file__).resolve().parents[2]
CASES = (("guava_long", "guava_long_math", "LongMath", "long", 64),
         ("guava_int", "guava_int_math", "IntMath", "int", 32),
         ("commons_long", "commons_arithmetic_utils", "ArithmeticUtils", "long", 64))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def run(inputs, output, *, replay=False):
    inputs, output = Path(inputs), Path(output)
    corpus = load(ROOT / "research/external/frozen_v2/CORPUS.json")
    if replay:
        require(output.is_dir(), "existing bridge experiment")
        manifest = load(output / "MANIFEST.json")
        files = {p.relative_to(output).as_posix() for p in output.rglob("*")
                 if p.is_file() and p.name != "MANIFEST.json"}
        require(set(manifest) == files, "exact bridge experiment file set")
        for relative, expected in manifest.items():
            require(sha((output / relative).read_bytes()) == expected, "changed experiment file: " + relative)
    else:
        require(not output.exists(), "new bridge experiment directory")
        output.mkdir(parents=True)
    rows = {}
    for case, source_id, class_name, word_type, width in CASES:
        raw = (inputs / (source_id + ".java")).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        require(blob == corpus["sources"][source_id]["blob"], "retained source identity: " + case)
        text = raw.decode("utf-8")
        selection = request({"class": class_name, "method": "isPowerOfTwo"}, word_type)
        directory = output / case
        if replay:
            certificate = load(directory / "certificate.json")
            require(load(directory / "request.json") == selection, "experiment selection")
            require((directory / "source.java").read_bytes() == raw, "experiment source")
        else:
            from .producer import derive
            certificate, _ = derive(text, selection)
            directory.mkdir()
            save(directory / "certificate.json", certificate)
            save(directory / "request.json", selection)
            (directory / "source.java").write_bytes(raw)
        ir, model = rebuild(text, selection, certificate)
        result = check(text, selection, certificate)
        if replay:
            require(load(directory / "result.json") == result, "bridge result equality")
            require(load(directory / "model.json") == model.data, "model inspection artifact equality")
            native_record = load(directory / "native.json")
        else:
            save(directory / "result.json", result)
            save(directory / "model.json", model.data)
            # Only the fresh producer/native path imports native helpers.
            from research.signed_predicates.experiment import population, native
            xs = population(width)
            _, _, _, declaration, _ = select(text, selection["entry"], word_type=word_type)
            ys = native(declaration, "isPowerOfTwo", word_type, width, xs)
            native_record = {"width": width, "inputs": xs, "outputs": ys,
                             "declaration_sha256": ir["declaration_sha256"],
                             "source_sha256": ir["source_sha256"],
                             "harness_sha256": sha((ROOT / "research/signed_predicates/experiment.py").read_bytes()),
                             "claim": "finite Java/source-IR/bridge correspondence; no target"}
            save(directory / "native.json", native_record)
        require(native_record["width"] == width
                and native_record["declaration_sha256"] == ir["declaration_sha256"]
                and native_record["source_sha256"] == ir["source_sha256"]
                and native_record["harness_sha256"] == sha((ROOT / "research/signed_predicates/experiment.py").read_bytes()),
                "native record source/harness binding")
        xs, ys = native_record["inputs"], native_record["outputs"]
        require(len(xs) == len(ys) and xs == sorted(set(xs))
                and all(type(y) is bool for y in ys), "native row count/types")
        mismatches = sum(y != evaluate(ir, x, width) or y != word_value(model, x, width)
                         for x, y in zip(xs, ys))
        require(mismatches == 0, "native/source-model mismatch")
        rows[case] = {"status": result["status"], "model_states": result["model_states"],
                      "positive_residual_states": result["positive_residual_states"],
                      "edges": result["checked_edges"], "source_sha256": ir["source_sha256"],
                      "model_sha256": model.sha256,
                      "certificate_sha256": sha((directory / "certificate.json").read_bytes()),
                      "native_inputs": len(xs), "native_mismatches": mismatches}
    summary = {"schema": "qkf-signed-source-model-development-v1", "cases": rows,
               "counts": {"source_model_verified": len(rows)},
               "native_inputs": sum(r["native_inputs"] for r in rows.values()),
               "native_mismatches": 0, "target_checked": False, "new_holdout": False,
               "frozen_v2_result_unchanged": True, "frozen_v3_run27_result_unchanged": True,
               "scope": "three retained PR24 development methods; no observation synthesis or target proof"}
    if replay:
        require(load(output / "SUMMARY.json") == summary, "experiment summary equality")
    else:
        save(output / "SUMMARY.json", summary)
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
