"""Pinned three-route experiment for observation-interface inference v1."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from research.observations.model import digest, require
from research.observations.run_io import read_json, write_json
from research.unified.schema import compile_target

from .checker import check
from .provenance import check_blob, check_engine

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "research/external/frozen_v1/CORPUS.json"
GRAAL = ROOT / "research/graal/native/IntegerStamp.java"


def targets():
    return {
        "jdk_lowbit": {
            "schema": "qkf-target-v1",
            "kind": "word_result",
            "source": {"entry": {"class": "Long", "method": "lowestOneBit"}, "word_type": "long"},
            "goal": ["lowest_set_bit"],
        },
        "lucene_power2": {
            "schema": "qkf-target-v1",
            "kind": "boolean_predicate",
            "source": {"entry": {"class": "BitUtil", "method": "isZeroOrPowerOfTwo"}, "word_type": "int"},
            "goal": ["popcount_le", 1],
        },
        "graal_successor": {
            "schema": "qkf-target-v1",
            "kind": "successor",
            "source": {"profile": "ascending"},
            "goal": {"claim": "cyclic_successor"},
        },
    }


def _sources(inputs):
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    jdk_raw = (Path(inputs) / "jdk_long.java").read_bytes()
    lucene_raw = (Path(inputs) / "lucene_bits.java").read_bytes()
    check_blob(jdk_raw, corpus["sources"]["jdk_long"])
    check_blob(lucene_raw, corpus["sources"]["lucene_bits"])
    return {
        "jdk_lowbit": jdk_raw.decode("utf-8"),
        "lucene_power2": lucene_raw.decode("utf-8"),
        "graal_successor": GRAAL.read_text(encoding="utf-8"),
    }


def run(inputs, output, *, replay=False):
    inputs, output = Path(inputs), Path(output)
    check_engine(ROOT)
    source_map, target_map = _sources(inputs), targets()

    if replay:
        require(output.is_dir(), "existing inference experiment directory")
    else:
        output.mkdir(parents=True, exist_ok=False)

    rows = {}
    for case_id in ("jdk_lowbit", "lucene_power2", "graal_successor"):
        source, target = source_map[case_id], target_map[case_id]
        directory = output / case_id
        if replay:
            require((directory / "source.java").read_bytes() == source.encode("utf-8"),
                    "retained inference source identity")
            require(read_json(directory / "target.json") == target, "retained inference target identity")
            certificate = read_json(directory / "certificate.json", package=True)
            result = check(source, target, certificate)
            require(digest(result) == digest(read_json(directory / "result.json", package=True)),
                    "recomputed inference result")
            existing_target_status = read_json(directory / "existing-target.json")["status"]
        else:
            from .producer import infer

            certificate, result = infer(source, target)
            directory.mkdir()
            (directory / "source.java").write_bytes(source.encode("utf-8"))
            write_json(directory / "target.json", target)
            write_json(directory / "certificate.json", certificate)
            write_json(directory / "result.json", result)

            if case_id == "graal_successor":
                from research.observations.run_producer import verify

                compiled = compile_target(target)
                old_result, package = verify(source, compiled["specification"], profile="ascending")
                require(package is not None and old_result["status"] == "certified",
                        "existing independent successor proof")
                existing_target_status = old_result["status"]
                write_json(directory / "existing-target.json", {
                    "status": old_result["status"],
                    "package_sha256": digest(package),
                })
            elif case_id == "jdk_lowbit":
                from research.wordexpr.producer import derive

                spec = compile_target(target)["specification"]
                _old, old_result = derive(source, spec)
                require(old_result["status"] == "certified", "existing lowbit proof")
                existing_target_status = old_result["status"]
                write_json(directory / "existing-target.json", {"status": old_result["status"]})
            else:
                from research.wordexpr.predicate_producer import derive

                spec = compile_target(target)["specification"]
                _old, old_result = derive(source, spec)
                require(old_result["status"] == "certified", "existing predicate proof")
                existing_target_status = old_result["status"]
                write_json(directory / "existing-target.json", {"status": old_result["status"]})

        require(result["status"] == "certified", "inference positive route: " + case_id)
        if case_id != "graal_successor":
            require(result["target_status"] == "certified", "direct inferred target closure")
        else:
            require(result["target_status"] == "not_checked"
                    and existing_target_status == "certified", "explicit successor v1 boundary")

        rows[case_id] = {
            "status": result["status"],
            "family": result["family"],
            "native_states": result["native_states"],
            "candidate_observations": result["candidate_observations"],
            "selected_observations": result["selected_observations"],
            "selected": result["selected"],
            "classes": result["classes"],
            "target_status": result["target_status"],
            "existing_target_status": existing_target_status,
            "certificate_sha256": digest(certificate),
        }

    summary = {
        "schema": "qkf-observation-inference-experiment-v1",
        "cases": rows,
        "counts": dict(Counter(r["status"] for r in rows.values())),
        "direct_target_closures": sum(r["target_status"] == "certified" for r in rows.values()),
        "existing_successor_crosscheck": rows["graal_successor"]["existing_target_status"],
        "frozen_v1_unchanged": True,
        "scope": (
            "source-derived equality projections over finite residual coordinates; "
            "not arbitrary observation-language synthesis or a new external benchmark"
        ),
    }

    if replay:
        require(digest(summary) == digest(read_json(output / "SUMMARY.json", package=True)),
                "inference replay summary identity")
    else:
        write_json(output / "SUMMARY.json", summary)
        write_json(output / "MANIFEST.json", {
            p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(output.rglob("*")) if p.is_file()
        })
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("inputs", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--replay", action="store_true")
    args = p.parse_args()
    print(json.dumps(run(args.inputs, args.output, replay=args.replay), sort_keys=True))


if __name__ == "__main__":
    main()
