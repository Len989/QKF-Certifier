"""Observation inference v2 experiment: richer library and direct successor target."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from research.observations.model import digest, require
from research.observations.run_io import read_json, write_json
from research.unified.schema import compile_target
from research.inference.provenance import check_blob, check_engine

from .v2_checker import check

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "research/external/frozen_v1/CORPUS.json"
ASCENDING = ROOT / "research/observations/evidence/ascending"


def low_target(entry):
    return {
        "schema": "qkf-target-v1",
        "kind": "word_result",
        "source": {"entry": entry, "word_type": "long"},
        "goal": ["lowest_set_bit"],
    }


def successor_target():
    return {
        "schema": "qkf-target-v1",
        "kind": "successor",
        "source": {"profile": "ascending"},
        "goal": {"claim": "cyclic_successor"},
    }


def order_cut_case():
    source = "class Demo { public static long f(long x) { return x + 3L; } }\n"
    target = {
        "schema": "qkf-target-v1",
        "kind": "word_result",
        "source": {"entry": {"class": "Demo", "method": "f"}, "word_type": "long"},
        "goal": ["equals", ["add", ["input"], ["const", 3]]],
    }
    return source, target


def cases(inputs):
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    jdk_raw = (Path(inputs) / "jdk_long.java").read_bytes()
    lucene_raw = (Path(inputs) / "lucene_bits.java").read_bytes()
    check_blob(jdk_raw, corpus["sources"]["jdk_long"])
    check_blob(lucene_raw, corpus["sources"]["lucene_bits"])

    order_source, order_target = order_cut_case()
    return {
        "jdk_lowbit": {
            "source": jdk_raw.decode("utf-8"),
            "target": low_target({"class": "Long", "method": "lowestOneBit"}),
            "expected": "certified",
            "group": "pinned_external_development",
        },
        "lucene_power2": {
            "source": lucene_raw.decode("utf-8"),
            "target": {
                "schema": "qkf-target-v1",
                "kind": "boolean_predicate",
                "source": {
                    "entry": {"class": "BitUtil", "method": "isZeroOrPowerOfTwo"},
                    "word_type": "int",
                },
                "goal": ["popcount_le", 1],
            },
            "expected": "certified",
            "group": "pinned_external_development",
        },
        "graal_original": {
            "source": (ASCENDING / "original.java").read_text(encoding="utf-8"),
            "target": successor_target(),
            "expected": "certified",
            "group": "retained_graal_control",
        },
        "graal_irrelevant_register": {
            "source": (ASCENDING / "irrelevant_register.java").read_text(encoding="utf-8"),
            "target": successor_target(),
            "expected": "certified",
            "group": "retained_graal_control",
        },
        "graal_clear_repair": {
            "source": (ASCENDING / "clear_repair.java").read_text(encoding="utf-8"),
            "target": successor_target(),
            "expected": "refuted",
            "group": "retained_graal_negative_control",
        },
        "order_cut_control": {
            "source": order_source,
            "target": order_target,
            "expected": "certified",
            "group": "constructed_richer_library_control",
        },
    }


def legacy_result(source, target):
    compiled = compile_target(target)
    if compiled["kind"] == "word_result":
        from research.wordexpr.producer import derive

        _certificate, result = derive(source, compiled["specification"])
        return result
    if compiled["kind"] == "boolean_predicate":
        from research.wordexpr.predicate_producer import derive

        _certificate, result = derive(source, compiled["specification"])
        return result

    from research.observations.run_producer import verify

    result, package = verify(source, compiled["specification"], profile="ascending")
    require(package is not None, "existing successor checker package")
    return result


def run(inputs, output, *, replay=False):
    inputs, output = Path(inputs), Path(output)
    check_engine()
    population = cases(inputs)

    if replay:
        require(output.is_dir(), "existing v2 inference experiment directory")
    else:
        output.mkdir(parents=True, exist_ok=False)

    rows = {}
    for case_id, case in population.items():
        source, target, expected = case["source"], case["target"], case["expected"]
        directory = output / case_id

        if replay:
            require((directory / "source.java").read_bytes() == source.encode("utf-8"),
                    "retained v2 inference source identity")
            require(read_json(directory / "target.json") == target,
                    "retained v2 inference target identity")
            certificate = read_json(directory / "certificate.json", package=True)
            result = check(source, target, certificate)
            require(digest(result) == digest(read_json(directory / "result.json", package=True)),
                    "recomputed v2 inference result")
            legacy = read_json(directory / "legacy-result.json", package=True)
        else:
            from .v2_producer import infer

            certificate, result = infer(source, target)
            legacy = legacy_result(source, target)
            directory.mkdir()
            (directory / "source.java").write_bytes(source.encode("utf-8"))
            write_json(directory / "target.json", target)
            write_json(directory / "certificate.json", certificate)
            write_json(directory / "result.json", result)
            write_json(directory / "legacy-result.json", legacy)

        require(result["status"] == expected, "v2 expected result: " + case_id)
        require(result["target_status"] == expected, "v2 direct target result: " + case_id)
        require(legacy["status"] == expected, "existing independent target result: " + case_id)

        selected_kinds = [row["kind"] for row in result["selected"]]
        if case_id == "order_cut_control":
            require("le" in selected_kinds, "richer order-cut observation selected")
        if case_id == "graal_irrelevant_register":
            labels = " ".join(row["label"] for row in result["selected"])
            require("register[0]" not in labels,
                    "irrelevant Graal toggle register pruned")

        rows[case_id] = {
            "status": result["status"],
            "group": case["group"],
            "family": result["family"],
            "native_states": result["native_states"],
            "candidate_observations": result["candidate_observations"],
            "selected_observations": result["selected_observations"],
            "selected": result["selected"],
            "classes": result["classes"],
            "target_status": result["target_status"],
            "target_product_states": result.get("target_product_states"),
            "target_reason": result.get("target_reason"),
            "legacy_status": legacy["status"],
            "certificate_sha256": digest(certificate),
        }

    counts = dict(Counter(row["status"] for row in rows.values()))
    require(counts == {"certified": 5, "refuted": 1}, "complete v2 inference population")
    summary = {
        "schema": "qkf-observation-inference-experiment-v2",
        "cases": rows,
        "counts": counts,
        "direct_target_results": len(rows),
        "direct_successor_certified": sum(
            row["family"] == "ascending-region" and row["target_status"] == "certified"
            for row in rows.values()
        ),
        "direct_successor_refuted": sum(
            row["family"] == "ascending-region" and row["target_status"] == "refuted"
            for row in rows.values()
        ),
        "richer_order_cut_selected": "le" in [
            item["kind"] for item in rows["order_cut_control"]["selected"]
        ],
        "frozen_v1_unchanged": True,
        "v1_semantics_preserved_by_separate_schema": True,
        "scope": (
            "richer finite source-derived residual projections and direct generic successor target; "
            "not arbitrary observation synthesis or a new blind benchmark"
        ),
    }

    if replay:
        require(digest(summary) == digest(read_json(output / "SUMMARY.json", package=True)),
                "v2 inference replay summary identity")
    else:
        write_json(output / "SUMMARY.json", summary)
        write_json(output / "MANIFEST.json", {
            p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(output.rglob("*")) if p.is_file()
        })
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.inputs, args.output, replay=args.replay), sort_keys=True))


if __name__ == "__main__":
    main()
