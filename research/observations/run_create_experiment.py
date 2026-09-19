"""Source-bound Graal create joint-carrier experiment on two pinned revisions.

The two revisions are provenance/transfer checks for the same algorithm body,
not two independent algorithms. Fresh mode derives both strong helper packages
and the caller certificate. Replay reconstructs source/specification externally
and invokes no producer.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from .create_kernel import check
from .create_source import read_source
from .create_spec import specification
from .model import digest, require
from .run_io import new_path, read_json, write_json
from .upstream_transfer import SEPARATOR, UPSTREAM, checked_inputs

SCHEMA = "qkf-graal-create-experiment-v1"


def _bundle(sources, name):
    return sources[name] + SEPARATOR + sources["jdk25"]


def _manifest(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != "MANIFEST.json"
    }


def run(inputs, output, *, replay=False, native=False, small_bits=4, samples=300):
    inputs, output = Path(inputs), Path(output)
    sources, provenance = checked_inputs(inputs)
    spec = specification()

    if replay:
        require(not native, "native validation is separate from no-search replay")
        require(output.is_dir(), "existing create experiment directory")
        require(read_json(output / "MANIFEST.json", package=True) == _manifest(output),
                "complete create experiment manifest")
        saved = output / "upstream"
        saved_sources, saved_provenance = checked_inputs(saved)
        require(saved_provenance == provenance, "replay external source identities")
        sources = saved_sources
    else:
        new_path(output).mkdir(parents=True, exist_ok=False)
        saved = output / "upstream"
        saved.mkdir()
        for name, text in sources.items():
            (saved / (name + ".java")).write_bytes(text.encode("utf-8"))

    cases = {}
    source_contracts = {}
    for name in ("graal_reference", "graal_revision"):
        source = _bundle(sources, name)
        contract = read_source(source)
        directory = output / name

        if replay:
            require((directory / "source.java").read_bytes() == source.encode("utf-8"),
                    "retained create source bytes")
            require(read_json(directory / "goal.json") == spec,
                    "retained independent create goal")
            certificate = read_json(directory / "certificate.json", package=True)
            result = check(source, spec, certificate)
            require(digest(read_json(directory / "result.json", package=True)) == digest(result),
                    "recomputed create result")
        else:
            from .create_producer import synthesize

            proposal = synthesize(source, spec)
            require(proposal.get("status") == "candidate"
                    and type(proposal.get("certificate")) is dict,
                    "fresh complete create proof")
            certificate = proposal["certificate"]
            result = check(source, spec, certificate)
            directory.mkdir()
            (directory / "source.java").write_bytes(source.encode("utf-8"))
            write_json(directory / "goal.json", spec)
            write_json(directory / "certificate.json", certificate)
            write_json(directory / "result.json", result)

        require(result["status"] == "certified"
                and result["all_supported_java_bit_widths"],
                "source-bound create certification")
        cases[name] = {
            "status": result["status"],
            "source_sha256": contract["source_sha256"],
            "source_contract_sha256": digest(contract),
            "certificate_sha256": digest(certificate),
            "carrier_states": result["carrier_states"],
            "updates_before_fixed_point_at_most":
                result["stabilization"]["updates_before_fixed_point_at_most"],
        }
        source_contracts[name] = contract

    # The selected create/helper algorithm is intentionally unchanged across
    # the two pinned Graal revisions. Full file hashes remain distinct.
    for field in ("methods", "primitives", "empty_factory"):
        require(
            source_contracts["graal_reference"][field]
            == source_contracts["graal_revision"][field],
            "same selected create algorithm across pinned revisions: " + field,
        )

    counts = dict(Counter(x["status"] for x in cases.values()))
    require(counts == {"certified": 2}, "complete create revision population")

    summary = {
        "schema": SCHEMA,
        "inputs": provenance,
        "cases": cases,
        "counts": counts,
        "scope": (
            "two revisions of the same Graal create algorithm with pinned OpenJDK primitive; "
            "not two independent programs and not arbitrary Java"
        ),
    }

    if replay:
        require(digest(summary) == digest(read_json(output / "SUMMARY.json", package=True)),
                "replayed create summary identity")
        return summary

    from .create_validation import validate

    validation = validate(native=native, small_bits=small_bits,
                          samples_per_width=samples)
    write_json(output / "SUMMARY.json", summary)
    write_json(output / "VALIDATION.json", validation)
    write_json(output / "MANIFEST.json", _manifest(output))
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("inputs", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--replay", action="store_true")
    p.add_argument("--native", action="store_true")
    p.add_argument("--small-bits", type=int, default=4, choices=range(1, 6))
    p.add_argument("--samples", type=int, default=300)
    args = p.parse_args()
    result = run(args.inputs, args.output, replay=args.replay, native=args.native,
                 small_bits=args.small_bits, samples=args.samples)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
