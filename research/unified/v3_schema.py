"""Additive signed target entry; the frozen qkf-target-v1 compiler is unchanged."""
from research.observations.model import digest, require
from research.signed_predicates.frontend import CONTRACT, GOAL_SCHEMA, goal
from .schema import compile_target as compile_v1

TARGET_SCHEMA = "qkf-target-v2"
SIGNED_KIND = "signed_boolean_predicate"
ENGINE = "observation-inference-v3"
PROOF_SCHEMA = "qkf-unified-proof-v2"
RESULT_SCHEMA = "qkf-unified-result-v2"


def compile_target(target):
    require(type(target) is dict, "v3 target object")
    if target.get("schema") == "qkf-target-v1":
        return compile_v1(target)
    require(set(target) == {"schema", "kind", "source", "goal"}
            and target["schema"] == TARGET_SCHEMA
            and target["kind"] == SIGNED_KIND, "v2 signed target fields")
    source = target["source"]
    require(type(source) is dict and set(source) == {"entry", "word_type"},
            "v2 signed target source fields")
    spec = {"schema": GOAL_SCHEMA, "contract": CONTRACT,
            "entry": source["entry"], "word_type": source["word_type"],
            "target": target["goal"]}
    goal(spec)
    return {"kind": SIGNED_KIND, "engine": ENGINE, "profile": "signed-terminal",
            "specification": spec, "target_sha256": digest(target),
            "specification_sha256": digest(spec)}
