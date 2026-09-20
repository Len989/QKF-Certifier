"""Versioned reduced-IR bridge; reuse PR28 local semantics and PR29 generic core.

The old source-model schema is never repurposed. A reduced model is meaningful
only after the source-to-reduced-IR certificate has independently replayed.
No code in this module is imported by the frozen/legacy source or target routes.
"""
from research.observations.model import ATOMIC_CERT_SCHEMA, Model, digest, integer, require
from research.signed_bridge.model import (ALPHABET, COMPLETION, EMPTY, MAX_STATES,
    CapacityExceeded, advance, finite_model, initial, state_value)
from .checker import rebuild as replay_reduction

MODEL_SCHEMA = "qkf-signed-reduced-source-model-v1"
OBS_SCHEMA = "qkf-signed-reduced-observations-v1"
ENGINE = "signed-reduction-before-carrier-v1"


def binding(selection, reduction, reduced):
    return {"source_sha256": reduced["source_sha256"], "request_sha256": digest(selection),
            "reduction_certificate_sha256": digest(reduction), "reduced_ir_sha256": digest(reduced),
            "original_ir_sha256": reduction["binding"]["original_ir_sha256"],
            "contract": selection["contract"], "completion": COMPLETION, "engine": ENGINE}


def model_from_states(selection, reduction, reduced, states):
    # Reuse the exact local step/terminal implementation, but NOT the old source
    # binding: this explicitly binds the new checked reduction dependency.
    native = finite_model(reduced, selection, states)
    return Model({**native.data, "binding": binding(selection, reduction, reduced)})


def rebuild_model(source, selection, certificate):
    require(type(certificate) is dict and set(certificate) == {
        "schema", "binding", "reduction", "carrier", "model"
    } and certificate["schema"] == MODEL_SCHEMA, "reduced model envelope fields")
    reduction = certificate["reduction"]
    original, reduced = replay_reduction(source, selection, reduction)
    require(digest(certificate["binding"]) == digest(binding(selection, reduction, reduced)),
            "reduced model binding")
    records = certificate["carrier"]
    require(type(records) is list and 0 < len(records) <= MAX_STATES, "bounded reduced carrier")
    states, seen = [], set()
    for i, row in enumerate(records):
        state = state_value(reduced, row)
        require(state not in seen, "duplicate reduced state")
        parent = row["parent"]
        if i == 0:
            require(parent is None and state == initial(reduced), "reduced empty initialization")
        else:
            require(state[0] and type(parent) is list and len(parent) == 2
                    and integer(parent[0], 0, i - 1)
                    and type(parent[1]) is str and parent[1] in ALPHABET,
                    "strictly earlier reduced reachability witness")
            require(advance(reduced, states[parent[0]], parent[1]) == state,
                    "reduced reachability replay")
        states.append(state)
        seen.add(state)
    model = model_from_states(selection, reduction, reduced, states)
    require(digest(certificate["model"]) == digest(model.data), "recomputed reduced model")
    return original, reduced, model


def check_model(source, selection, certificate):
    original, reduced, model = rebuild_model(source, selection, certificate)
    return {"schema": "qkf-signed-reduced-source-model-result-v1", "engine": ENGINE,
            "status": "source_model_verified", "claim": "source_reduced_model_equivalence",
            "source_sha256": original["source_sha256"], "request_sha256": digest(selection),
            "model_sha256": model.sha256, "model_states": len(model.states),
            "checked_edges": len(model.step), "completion": COMPLETION,
            "word_nodes_before": len(original["nodes"]), "word_nodes_after": len(reduced["nodes"]),
            "atoms_before": len(original["atoms"]), "atoms_after": len(reduced["atoms"]),
            "checked_reduction_steps": len(certificate["reduction"]["steps"]),
            "original_states_enumerated": 0, "max_source_states": MAX_STATES,
            "all_positive_widths_in_declared_profile": True,
            "target_checked": False, "lean_checked": False,
            "scope": "checked reduction followed by complete reachable reduced carrier; "
                     "retained frontend/residual semantics and Python rule/checker code are trusted"}


def check_observations(source, selection, certificate):
    from research.observations.checker import check as check_finite
    require(type(certificate) is dict and set(certificate) == {
        "schema", "source_model", "observations"
    } and certificate["schema"] == OBS_SCHEMA, "reduced observation envelope fields")
    original, _, model = rebuild_model(source, selection, certificate["source_model"])
    proof = certificate["observations"]
    require(type(proof) is dict and proof.get("schema") == ATOMIC_CERT_SCHEMA,
            "retained atomic observation format")
    checked = check_finite(model.data, proof)
    require(proof["blocks"][proof["initial"]] == [model.initial]
            and model.terminal[model.initial] == EMPTY, "protected empty class")
    return {"schema": "qkf-signed-reduced-observations-result-v1", "engine": ENGINE,
            "status": "source_observation_verified", "claim": "source_reduced_observation_equivalence",
            "source_sha256": original["source_sha256"], "request_sha256": digest(selection),
            "model_sha256": model.sha256, "model_states": len(model.states),
            "classes": len(proof["blocks"]), "positive_classes": len(proof["blocks"]) - 1,
            "derived_observations": len(proof["predicates"]), "observation": checked,
            "minimality_scope": "retained finite completion consumer, not a smallest formula or question set",
            "original_states_enumerated": 0, "completion": COMPLETION,
            "all_positive_widths_in_declared_profile": True,
            "target_checked": False, "lean_checked": False}


def build(source, selection, *, max_states=MAX_STATES, max_steps=512):
    from .producer import derive
    require(integer(max_states, 1, MAX_STATES), "model budget remains 1..64")
    reduction, _ = derive(source, selection, max_steps=max_steps)
    _, reduced = replay_reduction(source, selection, reduction)
    states, seen = [initial(reduced)], {initial(reduced)}
    records = [{"has_bits": False, "residual": list(states[0][1]), "parent": None}]
    for i, state in enumerate(states):
        for symbol in ALPHABET:
            following = advance(reduced, state, symbol)
            if following not in seen:
                if len(states) >= max_states:
                    raise CapacityExceeded("reduced reachable carrier budget (including initialization)")
                seen.add(following)
                states.append(following)
                records.append({"has_bits": True, "residual": list(following[1]), "parent": [i, symbol]})
    model = model_from_states(selection, reduction, reduced, states)
    certificate = {"schema": MODEL_SCHEMA, "binding": binding(selection, reduction, reduced),
                   "reduction": reduction, "carrier": records, "model": model.data}
    return certificate, check_model(source, selection, certificate)


def infer(source, selection, *, max_states=MAX_STATES, max_steps=512,
          max_observations=63, max_pullbacks=4096, max_classes=64):
    from research.observations.producer import synthesize
    from .producer import ReductionLimit
    require(integer(max_observations, 0, 63) and integer(max_pullbacks, 0, 100000)
            and integer(max_classes, 1, 64), "observation resource ceilings")
    try:
        bridge, _ = build(source, selection, max_states=max_states, max_steps=max_steps)
    except ReductionLimit as exc:
        return None, {"status": "budget_exhausted", "stage": "source_reduction", "reason": str(exc)}
    except CapacityExceeded as exc:
        return None, {"status": "budget_exhausted", "stage": "reduced_source_model", "reason": str(exc)}
    _, _, model = rebuild_model(source, selection, bridge)
    proposed = synthesize(model.data, row_encoding="atomic", max_observations=max_observations,
                          max_pullbacks=max_pullbacks, max_classes=max_classes)
    if proposed["status"] == "budget_exhausted":
        return None, {"status": "budget_exhausted", "stage": "observation_closure", "reason": proposed["reason"]}
    require(proposed["status"] == "candidate", "generic observation producer result")
    certificate = {"schema": OBS_SCHEMA, "source_model": bridge, "observations": proposed["certificate"]}
    return certificate, check_observations(source, selection, certificate)
