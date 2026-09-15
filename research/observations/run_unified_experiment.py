"""Reproduce all 18 existing target cases through the common research envelope.

Default: fresh source/target search, compared with the original checkers' saved
proofs. --retained-only: rebuild/replay envelopes from retained proofs without
producer imports. Each output case includes source.java, goal.json, package.json
and result.json. The caller must still select the external source and goal.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from .model import digest, require
from .run_io import new_path, write_json, write_run
from .run_package import check_package, create_package, explain_package
from .successor_spec import specification as successor_spec
from .upper_spec import specification as upper_spec

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "research/observations/evidence"


def load(path):
    return json.loads(path.read_bytes().decode("utf-8"))


def retained_cases():
    """Fixed case names/paths/goals, not executable instructions from evidence."""
    for name in ("original", "plus_one", "strict", "shared_input"):
        source = (EVIDENCE / "property" / f"{name}.java").read_bytes().decode("utf-8")
        model = load(EVIDENCE / "property" / f"{name}.source_certificate.json")
        for claim in ("maximum", "bound"):
            spec = upper_spec(claim)
            require(digest(load(EVIDENCE / "property" / f"{claim}.spec.json")) == digest(spec),
                    "independent retained descending target")
            proof = load(EVIDENCE / "property" / f"{name}.{claim}.certificate.json")
            expected = "certified" if name == "original" or claim == "bound" and name != "plus_one" else "refuted"
            yield {"id": f"descending.{name}.{claim}", "profile": "descending", "name": name,
                   "source": source, "spec": spec, "source_certificate": model,
                   "property_certificate": proof, "expected": expected}
    snapshot = load(EVIDENCE / "successor/SNAPSHOT.json")
    names = ("original", "clear_repair", "first_or", "first_four_bits", "irrelevant_register")
    require(set(snapshot["cases"]) == set(names), "complete ascending retained population")
    for name in names:
        source = (EVIDENCE / "ascending" / f"{name}.java").read_bytes().decode("utf-8")
        model = load(EVIDENCE / "ascending" / f"{name}.certificate.json")
        entry = snapshot["cases"][name]
        require(hashlib.sha256(source.encode("utf-8")).hexdigest() == entry["source_sha256"]
                and digest(model) == entry["source_certificate_sha256"], "retained ascending identities")
        for claim in ("cyclic_successor", "membership"):
            spec = successor_spec(claim)
            require(digest(snapshot["specifications"][claim]) == digest(spec), "independent retained ascending target")
            expected = "certified" if claim == "membership" or name in {"original", "irrelevant_register"} else "refuted"
            yield {"id": f"ascending.{name}.{claim}", "profile": "ascending", "name": name,
                   "source": source, "spec": spec, "source_certificate": model,
                   "property_certificate": entry["properties"][claim], "expected": expected}


def run(output, *, retained_only=False):
    output = new_path(output)
    output.mkdir(parents=True, exist_ok=False)
    results = {}
    for case in retained_cases():
        source, spec, profile = case["source"], case["spec"], case["profile"]
        retained = create_package(source, spec, profile, case["source_certificate"], case["property_certificate"])
        reference = check_package(source, spec, retained)
        if retained_only:
            result, package = reference, retained
        else:
            from .run_producer import verify
            result, package = verify(source, spec, profile=profile)
            require(package is not None, "common source/target producer budget")
            require(digest(result) == digest(reference), "fresh and retained checker results agree")
        replayed = check_package(source, spec, package)
        explanation = explain_package(source, spec, package)
        require(result["status"] == case["expected"] and replayed == result,
                "common and original target verdicts agree")
        require(explanation["status"] == result["status"] and explanation["explanation"]["replayed"],
                "explanation replays the same target")
        directory = output / case["id"]
        write_run(directory, result, package)
        (directory / "source.java").write_bytes(source.encode("utf-8"))
        write_json(directory / "goal.json", spec)
        write_json(directory / "explanation.json", explanation)
        results[case["id"]] = {
            "status": result["status"], "claim": result["claim"],
            "package_sha256": digest(package), "source_sha256": package["binding"]["source_sha256"],
            "specification_sha256": digest(spec),
            "package_bytes": (directory / "package.json").stat().st_size,
        }
    counts = dict(Counter(value["status"] for value in results.values()))
    require(len(results) == 18 and counts == {"certified": 11, "refuted": 7}, "complete 18-case regression")
    summary = {"schema": "qkf-common-run-regression-v1", "mode": "retained" if retained_only else "fresh",
               "cases": results, "counts": counts,
               "scope": "same existing target population; no new native, Lean or program coverage"}
    write_json(output / "SUMMARY.json", summary)
    write_json(output / "MANIFEST.json", {
        path.relative_to(output).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.rglob("*")) if path.is_file()
    })
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--retained-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.output, retained_only=args.retained_only), sort_keys=True))


if __name__ == "__main__":
    main()
