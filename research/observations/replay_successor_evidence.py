"""Replay retained ascending target certificates without search, SMT or Java.

The goals are supplied here independently as the two fixed supported targets;
the snapshot cannot choose or weaken them. Source paths are fixed by case name.
"""
import hashlib
import json
from pathlib import Path

from .model import digest, require
from .successor_kernel import check
from .successor_spec import CLAIMS, specification

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "research/observations/evidence/successor/SNAPSHOT.json"
CASES = ("original", "clear_repair", "first_or", "first_four_bits", "irrelevant_register")


def replay(snapshot):
    require(type(snapshot) is dict and set(snapshot) == {"schema", "specifications", "cases"}
            and snapshot["schema"] == "qkf-successor-replay-snapshot-v1", "successor snapshot schema")
    goals = {claim: specification(claim) for claim in CLAIMS}
    require(digest(snapshot["specifications"]) == digest(goals), "fixed independent replay goals")
    require(type(snapshot["cases"]) is dict and set(snapshot["cases"]) == set(CASES),
            "complete retained successor population")
    results = {}
    for name in CASES:
        entry = snapshot["cases"][name]
        require(type(entry) is dict and set(entry) == {
            "source", "source_certificate", "source_sha256", "source_certificate_sha256", "properties"
        }, "successor evidence fields")
        source_path = f"research/observations/evidence/ascending/{name}.java"
        certificate_path = f"research/observations/evidence/ascending/{name}.certificate.json"
        require(entry["source"] == source_path and entry["source_certificate"] == certificate_path,
                "fixed retained ascending source paths")
        source_bytes = (ROOT / source_path).read_bytes()
        source_certificate = json.loads((ROOT / certificate_path).read_bytes().decode("utf-8"))
        require(hashlib.sha256(source_bytes).hexdigest() == entry["source_sha256"], "retained source hash")
        require(digest(source_certificate) == entry["source_certificate_sha256"], "retained source certificate hash")
        require(type(entry["properties"]) is dict and set(entry["properties"]) == set(CLAIMS),
                "both retained independent properties")
        results[name] = {}
        for claim in CLAIMS:
            result = check(source_bytes.decode("utf-8"), source_certificate, goals[claim], entry["properties"][claim])
            expected = "certified" if claim == "membership" or name in {
                "original", "irrelevant_register"} else "refuted"
            require(result["status"] == expected, "retained experiment outcome")
            results[name][claim] = result
    return results


def main():
    try:
        results = replay(json.loads(SNAPSHOT.read_bytes().decode("utf-8")))
        print(json.dumps({"status": "replayed", "cases": results}, indent=2))
        return 0
    except (ValueError, TypeError, KeyError, IndexError, OSError, RecursionError) as exc:
        print(json.dumps({"status": "rejected", "error": str(exc)}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
