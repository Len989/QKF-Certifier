"""Check independently supplied successor/membership targets on five source variants.

The output contains standalone inputs/certificates plus a compact snapshot that
reuses the already retained ascending source evidence. Native comparisons are
explicitly bounded and remain distinct from closed-observation certificates.
"""
import argparse
import hashlib
import json
from pathlib import Path

from .ascending_kernel import check as check_source
from .ascending_producer import synthesize as source_synthesize
from .ascending_validation import validate
from .model import digest, require
from .run_ascending_experiment import variants
from .successor_kernel import check
from .successor_producer import synthesize
from .successor_spec import CLAIMS, specification


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--native", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    specs = {claim: specification(claim) for claim in CLAIMS}
    for claim, spec in specs.items():
        write(args.output / f"{claim}.spec.json", spec)
    results = {}
    snapshot = {"schema": "qkf-successor-replay-snapshot-v1", "specifications": specs, "cases": {}}
    old_evidence = Path(__file__).resolve().parent / "evidence" / "ascending"
    for name, source in variants().items():
        proposal = source_synthesize(source)
        require(proposal["status"] == "candidate", "ascending source observation budget")
        source_certificate = proposal["certificate"]
        source_result = check_source(source, source_certificate)
        # A compact replay snapshot can refer to existing evidence only after
        # byte/source-certificate agreement has actually been checked.
        require((old_evidence / f"{name}.java").read_bytes() == source.encode("utf-8"),
                "retained ascending source identity")
        require(digest(json.loads((old_evidence / f"{name}.certificate.json").read_text(encoding="utf-8")))
                == digest(source_certificate), "retained ascending certificate identity")
        (args.output / f"{name}.java").write_bytes(source.encode("utf-8"))
        write(args.output / f"{name}.source_certificate.json", source_certificate)
        target_results = {}
        proofs = {}
        for claim, spec in specs.items():
            proposal = synthesize(source, source_certificate, spec)
            require(proposal["status"] == "candidate", "successor joint-observation budget")
            certificate = proposal["certificate"]
            result = check(source, source_certificate, spec, certificate)
            expected = "certified" if claim == "membership" or name in {
                "original", "irrelevant_register"} else "refuted"
            require(result["status"] == expected, "independent successor experiment outcome")
            target_results[claim] = result
            proofs[claim] = certificate
            write(args.output / f"{name}.{claim}.certificate.json", certificate)
        validation = validate(source, source_certificate, native=args.native)
        results[name] = {"source_model": source_result, "properties": target_results, "validation": validation}
        snapshot["cases"][name] = {
            "source": f"research/observations/evidence/ascending/{name}.java",
            "source_certificate": f"research/observations/evidence/ascending/{name}.certificate.json",
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "source_certificate_sha256": digest(source_certificate), "properties": proofs,
        }
        print(json.dumps({"case": name, "properties": target_results, "validation": validation}), flush=True)
    budget = synthesize(variants()["original"], source_synthesize(variants()["original"])["certificate"],
                        specs["cyclic_successor"], max_states=1)
    require(budget["status"] == "budget_exhausted" and budget["certificate"] is None,
            "honest successor producer budget")
    write(args.output / "RESULTS.json", results)
    write(args.output / "SNAPSHOT.json", snapshot)
    write(args.output / "BUDGET.json", budget)
    write(args.output / "MANIFEST.json", {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                          for p in sorted(args.output.iterdir()) if p.is_file()})


if __name__ == "__main__":
    main()
