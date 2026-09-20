"""Check a composed source/model/observation certificate without running search.

All model semantics are reconstructed through the accepted PR28 bridge. The
unchanged generic checker verifies question origins, stability, atomic rows and
separators. Its finite-model minimality is relative to the completion consumer,
including 'not-a-word', not to a user's property or to the number of questions.
"""
from research.observations.checker import check as check_finite
from research.observations.model import ATOMIC_CERT_SCHEMA, digest, require
from research.signed_bridge.checker import rebuild as rebuild_source
from research.signed_bridge.model import COMPLETION, EMPTY

SCHEMA = "qkf-signed-source-observations-v1"
ENGINE = "signed-source-observation-closure-v1"
CONSUMER = "source-terminal-and-empty-distinction-v1"


def binding(selection, bridge, model):
    return {"source_sha256": bridge["binding"]["source_sha256"],
            "request_sha256": digest(selection), "model_sha256": model.sha256,
            "source_model_certificate_sha256": digest(bridge),
            "completion": COMPLETION, "consumer": CONSUMER, "engine": ENGINE}


def rebuild(source, selection, certificate):
    require(type(certificate) is dict and set(certificate) == {
        "schema", "binding", "source_model", "observations"
    } and certificate["schema"] == SCHEMA, "source observation envelope fields")
    bridge = certificate["source_model"]
    ir, model = rebuild_source(source, selection, bridge)
    require(digest(certificate["binding"]) == digest(binding(selection, bridge, model)),
            "source observation envelope binding")
    proof = certificate["observations"]
    require(type(proof) is dict and proof.get("schema") == ATOMIC_CERT_SCHEMA,
            "source observation route requires the retained atomic encoding")
    observation = check_finite(model.data, proof)
    return ir, model, observation


def check(source, selection, certificate):
    ir, model, observation = rebuild(source, selection, certificate)
    proof = certificate["observations"]
    k = len(proof["blocks"])
    empty_class = proof["initial"]
    require(proof["blocks"][empty_class] == [model.initial]
            and model.terminal[model.initial] == EMPTY, "protected initialization class")
    return {"schema": "qkf-signed-source-observations-result-v1", "engine": ENGINE,
            "status": "source_observation_verified", "claim": "source_observation_equivalence",
            "source_sha256": ir["source_sha256"], "request_sha256": digest(selection),
            "model_sha256": model.sha256, "completion": COMPLETION, "consumer": CONSUMER,
            "model_states": len(model.states), "classes": k, "positive_classes": k - 1,
            "initialization_classes": 1, "derived_observations": len(proof["predicates"]),
            "checked_source_edges": len(model.step), "checked_factor_edges": len(proof["cells"]),
            "separating_class_pairs": len(proof["separators"]),
            "max_witness_length": observation["max_witness_length"],
            "minimality": observation["minimality"],
            "minimum_question_count_claimed": False, "shortest_witnesses_claimed": False,
            "observation": observation, "all_positive_widths_in_declared_profile": True,
            "target_checked": False, "lean_checked": False,
            "trust": "retained restricted frontend/residual semantics and Python bridge/observation checkers",
            "scope": "source-bound exact finite consumer factor with explicit empty trace; not a target proof"}
