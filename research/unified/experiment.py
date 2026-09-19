"""Five-case unified runner smoke test over all four routed proof profiles."""

from research.observations.run_unified_experiment import retained_cases

from .checker import check
from .producer import prove


WORD_SOURCE = "class Demo { public static long low(long x) { return x & -x; } }\n"
PRED_SOURCE = "class Demo { public static boolean p(int x) { return (x & (x - 1)) == 0; } }\n"

WORD_TARGET = {
    "schema": "qkf-target-v1",
    "kind": "word_result",
    "source": {"entry": {"class": "Demo", "method": "low"}, "word_type": "long"},
    "goal": ["lowest_set_bit"],
}
PRED_TARGET = {
    "schema": "qkf-target-v1",
    "kind": "boolean_predicate",
    "source": {"entry": {"class": "Demo", "method": "p"}, "word_type": "int"},
    "goal": ["popcount_le", 1],
}
SUCCESSOR_TARGET = {
    "schema": "qkf-target-v1",
    "kind": "successor",
    "source": {"profile": "ascending"},
    "goal": {"claim": "cyclic_successor"},
}
MAXIMUM_TARGET = {
    "schema": "qkf-target-v1",
    "kind": "masked_bound",
    "source": {"profile": "descending"},
    "goal": {"claim": "maximum"},
}


def retained(profile, name, claim):
    for case in retained_cases():
        if case["profile"] == profile and case["name"] == name and case["spec"]["claim"] == claim:
            return case
    raise AssertionError("retained case not found")


def run():
    cases = [
        ("word.lowbit", WORD_SOURCE, WORD_TARGET, "certified"),
        ("predicate.power2", PRED_SOURCE, PRED_TARGET, "certified"),
    ]
    asc = retained("ascending", "original", "cyclic_successor")
    desc = retained("descending", "original", "maximum")
    strict = retained("descending", "strict", "maximum")
    cases += [
        ("ascending.successor", asc["source"], SUCCESSOR_TARGET, "certified"),
        ("descending.maximum", desc["source"], MAXIMUM_TARGET, "certified"),
        ("descending.strict", strict["source"], MAXIMUM_TARGET, "refuted"),
    ]
    results = {}
    for case_id, source, target, expected in cases:
        result, proof = prove(source, target)
        if result["status"] != expected or proof is None:
            raise AssertionError(case_id + ": unexpected unified result")
        if check(source, target, proof) != result:
            raise AssertionError(case_id + ": replay mismatch")
        results[case_id] = {
            "status": result["status"],
            "kind": result["kind"],
            "engine": result["engine"],
            "all_positive_widths": result["all_positive_widths"],
        }
    return {
        "schema": "qkf-unified-experiment-v1",
        "cases": results,
        "counts": {
            "certified": sum(v["status"] == "certified" for v in results.values()),
            "refuted": sum(v["status"] == "refuted" for v in results.values()),
        },
        "scope": "existing proof engines only; no new source language, theorem, or external coverage",
    }


def main():
    import json

    print(json.dumps(run(), sort_keys=True))


if __name__ == "__main__":
    main()
