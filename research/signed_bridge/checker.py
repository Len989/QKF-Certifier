"""Independent source-to-model replay; no producer or partition search.

Earlier-parent witnesses prove that every supplied state is reachable. Initial
coverage and source-recomputed closure prove that no reachable state is missing.
Exact typed comparison with a reconstructed finite model protects all labels,
completion information and transition destinations, even against rehashed edits.
"""
from research.observations.model import digest, integer, require
from .model import (ALPHABET, COMPLETION, MAX_STATES, SCHEMA, advance, binding,
                    finite_model, initial, read, state_value)


def rebuild(source, selection, certificate):
    require(type(certificate) is dict and set(certificate) == {
        "schema", "binding", "ir", "carrier", "model"
    } and certificate["schema"] == SCHEMA, "signed source-model certificate fields")
    ir = read(source, selection)
    require(digest(certificate["binding"]) == digest(binding(selection, ir)),
            "source/request/contract binding")
    require(digest(certificate["ir"]) == digest(ir), "source-derived IR changed")
    records = certificate["carrier"]
    require(type(records) is list and 0 < len(records) <= MAX_STATES,
            "bounded complete source-model carrier")
    states, seen = [], set()
    for i, row in enumerate(records):
        state = state_value(ir, row)
        require(state not in seen, "duplicate source state including completion flag")
        parent = row["parent"]
        if i == 0:
            require(parent is None and state == initial(ir), "exact empty initialization")
        else:
            require(state[0], "only initialization may have no bits")
            require(type(parent) is list and len(parent) == 2
                    and integer(parent[0], 0, i - 1)
                    and type(parent[1]) is str and parent[1] in ALPHABET,
                    "strictly earlier reachability witness")
            require(advance(ir, states[parent[0]], parent[1]) == state,
                    "source reachability witness does not replay")
        seen.add(state)
        states.append(state)
    model = finite_model(ir, selection, states)
    # Digest compares JSON types too (False must not equal integer zero).
    # The hash is only an equality check with freshly reconstructed semantics,
    # not acceptance of the producer's independently chosen table.
    require(digest(certificate["model"]) == digest(model.data),
            "source-reconstructed model differs: labels, cells, alphabet or binding")
    return ir, model


def check(source, selection, certificate):
    ir, model = rebuild(source, selection, certificate)
    return {"schema": "qkf-signed-source-model-result-v1",
            "status": "source_model_verified", "claim": "source_model_equivalence",
            "source_sha256": ir["source_sha256"], "request_sha256": digest(selection),
            "model_sha256": model.sha256, "completion": COMPLETION,
            "model_states": len(model.states), "positive_residual_states": len(model.states) - 1,
            "distinct_residual_vectors": len({tuple(row["residual"]) for row in certificate["carrier"]}),
            "checked_edges": len(model.step), "initialization_only_states": 1,
            "all_positive_widths_in_declared_profile": True,
            "target_checked": False, "lean_checked": False,
            "trust": "retained restricted frontend and modular signed residual semantics; Python checker",
            "scope": "exact reachable source model, not a target proof, minimal factor or arbitrary Java theorem"}


def check_observations(source, selection, certificate, observation_certificate):
    """Bind an externally produced observation proof to the rebuilt source.

PR28 does not run or modify the observation producer. Its generic-model proof
is accepted only *after* the source bridge; bundled tables are never trusted.
"""
    from research.observations.checker import check as check_finite
    _, model = rebuild(source, selection, certificate)
    result = check_finite(model.data, observation_certificate)
    return {"status": "source_observation_verified", "target_checked": False,
            "model_sha256": model.sha256, "observation": result,
            "scope": "source-bound finite-model observations, including empty/nonempty distinction; not a target proof"}
