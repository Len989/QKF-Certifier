"""Compile qkf-target-v1 requests into existing independently checked goals."""

from research.observations.model import digest, require

SCHEMA = "qkf-target-v1"
RESULT_SCHEMA = "qkf-unified-result-v1"
PROOF_SCHEMA = "qkf-unified-proof-v1"
EXIT_CODES = {
    "certified": 0,
    "refuted": 1,
    "unsupported": 2,
    "budget_exhausted": 2,
    "invalid_certificate": 3,
    "input_error": 64,
    "internal_error": 70,
}

ENGINES = {
    "word_result": "wordexpr-v1",
    "boolean_predicate": "word-predicate-v1",
    "successor": "typed-observation-ascending-v1",
    "masked_bound": "typed-observation-descending-v1",
}


def _entry(value):
    require(
        type(value) is dict
        and set(value) == {"class", "method"}
        and all(type(value[k]) is str and value[k] for k in ("class", "method")),
        "target source entry",
    )
    return {"class": value["class"], "method": value["method"]}


def compile_target(target):
    """Validate one closed external schema and derive an existing engine spec."""
    require(type(target) is dict and target.get("schema") == SCHEMA, "unified target schema")
    kind = target.get("kind")
    require(type(kind) is str and kind in ENGINES, "unified target kind")
    require(set(target) == {"schema", "kind", "source", "goal"}, "unified target fields")

    if kind == "word_result":
        source = target["source"]
        require(type(source) is dict and set(source) == {"entry", "word_type"}, "word source fields")
        require(source.get("word_type") == "long", "word_result currently requires long")
        spec = {
            "schema": "qkf-word-expression-goal-v1",
            "contract": "modular-lsb-word-expressions-v1",
            "entry": _entry(source["entry"]),
            "target": target["goal"],
        }
        from research.wordexpr.frontend import goal

        goal(spec)
        profile = None

    elif kind == "boolean_predicate":
        source = target["source"]
        require(type(source) is dict and set(source) == {"entry", "word_type"}, "predicate source fields")
        require(source.get("word_type") in {"int", "long"}, "predicate word type")
        spec = {
            "schema": "qkf-word-predicate-goal-v1",
            "contract": "modular-lsb-word-predicates-v1",
            "entry": _entry(source["entry"]),
            "word_type": source["word_type"],
            "target": target["goal"],
        }
        from research.wordexpr.predicate_frontend import goal

        goal(spec)
        profile = None

    elif kind == "successor":
        require(target["source"] == {"profile": "ascending"}, "successor source profile")
        require(type(target["goal"]) is dict and set(target["goal"]) == {"claim"}, "successor goal fields")
        from research.observations.target_templates import template

        spec = template("ascending", target["goal"]["claim"])
        profile = "ascending"

    else:
        require(target["source"] == {"profile": "descending"}, "masked source profile")
        require(type(target["goal"]) is dict and set(target["goal"]) == {"claim"}, "masked goal fields")
        from research.observations.target_templates import template

        spec = template("descending", target["goal"]["claim"])
        profile = "descending"

    return {
        "kind": kind,
        "engine": ENGINES[kind],
        "profile": profile,
        "specification": spec,
        "target_sha256": digest(target),
        "specification_sha256": digest(spec),
    }
