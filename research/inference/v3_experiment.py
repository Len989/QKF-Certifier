"""Post-holdout development of signed inference and the unified v3 route.

Native validation runs only during production.  Replay checks proof envelopes,
reference certificates and retained file identities without importing producers
or native tools.  Retained native records are evidence, not newly executed tests.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from research.observations.model import digest, require
from research.signed_predicates.checker import check as check_reference
from research.signed_predicates.frontend import target_value
from research.signed_predicates.semantics import evaluate
from research.unified.v3 import check
from research.unified.v3_schema import compile_target

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "research/external/frozen_v2"
EXTERNAL = (
    ("guava_long", "guava_long_math", "LongMath", "long"),
    ("guava_int", "guava_int_math", "IntMath", "int"),
    ("commons_long", "commons_arithmetic_utils", "ArithmeticUtils", "long"),
)


def load(path):
    from research.unified.run import load_json
    return load_json(path)


def save(path, value):
    from research.unified.run import save_json
    save_json(path, value)


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def engine_identity():
    expected = load(FROZEN / "ENGINE.json")
    actual = {p: git_blob((ROOT / p).read_bytes()) for p in expected["git_blobs"]}
    require(actual == expected["git_blobs"], "frozen v2 engine files changed")
    return {"commit": expected["commit"], "tree": expected["tree"], "file_count": len(actual)}


def population(inputs):
    corpus = load(FROZEN / "CORPUS.json")
    identities = load(inputs / "IDENTITIES.json")
    require(set(identities) == set(corpus["sources"]), "complete retained input identities")
    texts = {}
    for name, identity in corpus["sources"].items():
        raw = (inputs / (name + ".java")).read_bytes()
        require(len(raw) <= corpus["budgets"]["source_bytes"], "retained source byte budget")
        require(git_blob(raw) == identity["blob"] == identities[name]["blob"],
                "retained external source Git blob: " + name)
        texts[name] = raw.decode("utf-8")
    cases = {}
    for case_id, name, class_name, word_type in EXTERNAL:
        cases[case_id] = {"source": texts[name], "target": target(class_name, "isPowerOfTwo", word_type),
                          "expected": "certified", "group": "post_holdout_external_development",
                          "reference": True}
    for word_type in ("int", "long"):
        s = "class Demo { public static boolean f(" + word_type + " x) { return x != 0 && (x & (x - 1)) == 0; } }"
        cases["sign_bit_mutant_" + word_type] = {"source": s, "target": target("Demo", "f", word_type),
            "expected": "refuted", "group": "constructed_negative_control", "reference": False}
    cases["zero_guard_mutant"] = {
        "source": "class Demo { public static boolean f(int x) { return x >= 0 && (x & (x - 1)) == 0; } }",
        "target": target("Demo", "f", "int"), "expected": "refuted",
        "group": "constructed_negative_control", "reference": False}
    cases["unsupported_shift"] = {
        "source": "class Demo { public static boolean f(int x) { return (x >> 1) > 0; } }",
        "target": target("Demo", "f", "int"), "expected": "unsupported",
        "group": "capability_boundary", "reference": False}
    cases["feature_budget_zero"] = {
        "source": "class Demo { public static boolean f(int x) { return x > 0 && (x & (x - 1)) == 0; } }",
        "target": target("Demo", "f", "int"), "expected": "budget_exhausted",
        "group": "budget_boundary", "reference": False, "budgets": {"max_features": 0}}
    return cases


def target(class_name, method, word_type):
    return {"schema": "qkf-target-v2", "kind": "signed_boolean_predicate",
            "source": {"entry": {"class": class_name, "method": method}, "word_type": word_type},
            "goal": ["and", ["positive"], ["popcount_eq", 1]]}


def native_record(source, target_request, *, external):
    # The only native dependency in this module is intentionally lazy.
    from research.signed_predicates.experiment import native, population as native_population
    from research.signed_predicates.frontend import read_source, select
    spec = compile_target(target_request)["specification"]
    word_type = spec["word_type"]
    width = 32 if word_type == "int" else 64
    _body, _parameter, _final, declaration, _span = select(source, spec["entry"], word_type=word_type)
    ir = read_source(source, spec["entry"], word_type)
    if external:
        xs = native_population(width)
    else:
        mask = (1 << width) - 1
        xs = sorted(set(range(256)) | {mask, 1 << (width - 1), (1 << (width - 1)) - 1})
    ys = native(declaration, spec["entry"]["method"], word_type, width, xs)
    ir_mismatches, goal_mismatches = 0, 0
    for x, y in zip(xs, ys):
        ir_mismatches += y != evaluate(ir, x, width)
        goal_mismatches += y != target_value(spec["target"], x.bit_count(), x >> (width - 1))
    require(ir_mismatches == 0, "native method and whole-word IR differ")
    return {"inputs": len(xs), "source_ir_mismatches": ir_mismatches,
            "target_mismatches": goal_mismatches, "java_width": width,
            "inputs_sha256": digest(xs), "outputs_sha256": digest(ys),
            "compiled_release": 17,
            "scope": "selected exact method declaration; finite native validation, not the all-width proof"}


def run(inputs, output, *, replay=False):
    inputs, output = Path(inputs), Path(output)
    engine = engine_identity()
    cases = population(inputs)
    if replay:
        require(output.is_dir(), "existing v3 experiment directory")
        manifest = load(output / "MANIFEST.json")
        actual = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(output.rglob("*")) if p.is_file() and p.name != "MANIFEST.json"}
        require(actual == manifest, "v3 experiment retained file identities")
    else:
        output.mkdir(parents=True, exist_ok=False)
    rows = {}
    for case_id, case in cases.items():
        directory = output / case_id
        source, request = case["source"], case["target"]
        if replay:
            require((directory / "source.java").read_bytes() == source.encode("utf-8"), "v3 retained source")
            require(digest(load(directory / "target.json")) == digest(request), "v3 retained target")
            saved = load(directory / "result.json")
            if case["expected"] in {"certified", "refuted"}:
                result = check(source, request, load(directory / "proof.json"))
                require(digest(result) == digest(saved), "v3 recomputed result")
            else:
                # Unsupported/exhaustion are retained producer diagnostics, not proofs.
                require(not (directory / "proof.json").exists(), "no proof for a boundary diagnostic")
                result = saved
        else:
            from research.unified.v3 import prove
            result, proof = prove(source, request, budgets=case.get("budgets"))
            directory.mkdir()
            (directory / "source.java").write_bytes(source.encode("utf-8"))
            save(directory / "target.json", request)
            save(directory / "result.json", result)
            if proof is not None:
                save(directory / "proof.json", proof)
        require(result["status"] == case["expected"], "v3 expected verdict: " + case_id)
        row = {"status": result["status"], "group": case["group"],
               "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest()}
        if result["status"] in {"certified", "refuted"}:
            inner = result["inner"]
            if replay:
                record = load(directory / "native.json")
            else:
                record = native_record(source, request, external=case["reference"])
                save(directory / "native.json", record)
            require(record["source_ir_mismatches"] == 0, "retained native/source agreement")
            require((record["target_mismatches"] == 0) == (result["status"] == "certified"),
                    "native target validation or negative control")
            row.update({k: inner[k] for k in ("native_states", "candidate_observations",
                                             "selected_observations", "selected", "classes")})
            row.update({"target_product_states": inner.get("target_product_states"),
                        "witness_width": inner.get("witness_width"), "native": record,
                        "certificate_sha256": digest(load(directory / "proof.json"))})
        if case["reference"]:
            spec = compile_target(request)["specification"]
            if replay:
                ref = check_reference(source, spec, load(directory / "reference-certificate.json"))
                require(digest(ref) == digest(load(directory / "reference-result.json")),
                        "v3 independent PR24 reference replay")
            else:
                from research.signed_predicates.producer import derive
                ref_cert, ref = derive(source, spec)
                save(directory / "reference-certificate.json", ref_cert)
                save(directory / "reference-result.json", ref)
            require(ref["status"] == "certified", "PR24 reference verdict")
            require((row["native_states"], row["classes"], row["target_product_states"]) == (6, 4, 5),
                    "v3 signed development factor sizes")
            require(row["classes"] == ref["source"]["classes"], "inferred and reference class counts")
            row["reference_classes"] = ref["source"]["classes"]
        rows[case_id] = row
    counts = dict(Counter(row["status"] for row in rows.values()))
    require(counts == {"certified": 3, "refuted": 3, "unsupported": 1, "budget_exhausted": 1},
            "complete v3 development population")
    external_rows = [row for row in rows.values() if row["group"] == "post_holdout_external_development"]
    summary = {"schema": "qkf-observation-inference-experiment-v3", "cases": rows, "counts": counts,
               "frozen_engine": engine, "development_after_frozen_v2": True,
               "frozen_v2_historical_result_unchanged": True,
               "external_native_inputs": sum(row["native"]["inputs"] for row in external_rows),
               "external_native_mismatches": sum(row["native"]["target_mismatches"] for row in external_rows),
               "native_source_ir_mismatches": sum(row.get("native", {}).get("source_ir_mismatches", 0) for row in rows.values()),
               "proof_cases_independently_replayed": 6,
               "boundary_diagnostics_and_native_records_retained_not_reexecuted_on_replay": True,
               "scope": "post-holdout development and constructed controls; not a new holdout, new Lean theorem or arbitrary observation-language synthesis"}
    if replay:
        require(digest(summary) == digest(load(output / "SUMMARY.json")), "v3 replay summary identity")
    else:
        save(output / "SUMMARY.json", summary)
        save(output / "MANIFEST.json", {
            p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(output.rglob("*")) if p.is_file()
        })
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.inputs, args.output, replay=args.replay), sort_keys=True))


if __name__ == "__main__":
    main()
