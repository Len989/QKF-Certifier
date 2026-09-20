"""Check every derivative branch and terminal; never enumerate the old carrier."""
from research.observations.model import ATOMIC_CERT_SCHEMA, MODEL_SCHEMA as FINITE_SCHEMA
from research.observations.model import Model, digest, integer, require
from research.signed_reduction.checker import rebuild as replay_reduction
from .local import (ALPHABET, COMPLETION, EMPTY, ENGINE, MODEL_SCHEMA, OBS_SCHEMA,
                    MAX_STATES, MAX_TOTAL_STEPS, binding, initial, replay_edge, terminal, view)


def rebuild(source, selection, certificate):
    require(type(certificate) is dict and set(certificate) == {
        "schema", "binding", "reduction", "states", "parents", "edges", "model"
    } and certificate["schema"] == MODEL_SCHEMA, "guarded source model envelope")
    original, ir = replay_reduction(source, selection, certificate["reduction"])
    expected_binding = binding(selection, certificate["reduction"], ir)
    require(digest(certificate["binding"]) == digest(expected_binding), "guarded source binding")
    states, parents, edges = certificate["states"], certificate["parents"], certificate["edges"]
    require(type(states) is list and 0 < len(states) <= MAX_STATES, "bounded covered carrier")
    require(type(parents) is list and len(parents) == len(states), "reachability parent coverage")
    require(type(edges) is list and len(edges) == 2 * len(states), "every binary branch required")
    for state in states:
        view(ir, state)
    keys = [digest(s) for s in states]
    require(len(set(keys)) == len(keys), "duplicate guarded residual description")
    require(keys[0] == digest(initial(ir)) and parents[0] is None, "exact source initial coverage")
    require(all(s["has_bits"] for s in states[1:]), "only one empty initialization")
    steps, labels, indexed = [], {}, {}
    total_steps, guards, discarded = 0, 0, 0
    names = ["g%03d" % i for i in range(len(states))]
    for i, state in enumerate(states):
        labels[names[i]] = terminal(ir, state)
        for k, symbol in enumerate(ALPHABET):
            edge = edges[2*i+k]
            require(type(edge) is dict and set(edge) == {"state", "symbol", "next", "proof"}
                    and type(edge["state"]) is int and edge["state"] == i
                    and type(edge["symbol"]) is str and edge["symbol"] == symbol
                    and integer(edge["next"], 1, len(states)-1), "typed exhaustive branch record")
            proof = edge["proof"]
            following = replay_edge(ir, state, symbol, proof)
            require(digest(following) == keys[edge["next"]], "local residual simulation failed")
            total_steps += len(proof["steps"])
            require(total_steps <= MAX_TOTAL_STEPS, "total local proof ceiling")
            guards += len(proof["retired_equalities"])
            discarded += len(proof["dropped"]["nodes"])
            indexed[i, symbol] = edge["next"]
            steps.append({"state": names[i], "symbol": symbol, "output": "_", "next": names[edge["next"]]})
    for i, parent in enumerate(parents[1:], 1):
        require(type(parent) is list and len(parent) == 2 and integer(parent[0], 0, i-1)
                and type(parent[1]) is str and parent[1] in ALPHABET, "earlier covered reachability parent")
        require(indexed[parent[0], parent[1]] == i, "covered state is not justified as reachable")
    model = Model({"schema": FINITE_SCHEMA, "states": names, "alphabet": list(ALPHABET),
                   "outputs": ["_"], "initial": names[0], "terminal": labels,
                   "steps": steps, "binding": expected_binding})
    require(digest(certificate["model"]) == digest(model.data), "source-recomputed coverage model")
    metrics = {"covered_states": len(states), "checked_binary_branches": len(edges),
               "checked_guard_occurrences": guards, "discarded_word_slots_across_edges": discarded,
               "checked_local_rewrites": total_steps,
               "original_states_enumerated": 0,
               "peak_live_word_slots": max(len(s["projection"]["nodes"]) for s in states),
               "peak_live_atoms": max(len(s["projection"]["atoms"]) for s in states)}
    return original, ir, model, metrics


def check_model(source, selection, certificate):
    original, _, model, metrics = rebuild(source, selection, certificate)
    return {"schema": "qkf-signed-guarded-model-result-v1", "engine": ENGINE,
            "status": "source_model_verified", "claim": "source_guarded_residual_equivalence",
            "source_sha256": original["source_sha256"], "request_sha256": digest(selection),
            "model_sha256": model.sha256, "coverage": metrics, "completion": COMPLETION,
            "all_positive_widths_in_declared_profile": True, "target_checked": False, "lean_checked": False}


def rebuild_observations(source, selection, certificate):
    from research.observations.checker import check as finite_check
    require(type(certificate) is dict and set(certificate) == {"schema", "source_model", "observations"}
            and certificate["schema"] == OBS_SCHEMA, "guarded observation envelope")
    original, _, model, metrics = rebuild(source, selection, certificate["source_model"])
    proof = certificate["observations"]
    require(type(proof) is dict and proof.get("schema") == ATOMIC_CERT_SCHEMA, "atomic observation format")
    observed = finite_check(model.data, proof)
    require(proof["blocks"][proof["initial"]] == [model.initial]
            and model.terminal[model.initial] == EMPTY, "protected empty observation")
    return original, model, observed, metrics


def check_observations(source, selection, certificate):
    original, model, observed, metrics = rebuild_observations(source, selection, certificate)
    proof = certificate["observations"]
    return {"schema": "qkf-signed-guarded-observations-result-v1", "engine": ENGINE,
            "status": "source_observation_verified", "claim": "source_guarded_observation_equivalence",
            "source_sha256": original["source_sha256"], "request_sha256": digest(selection),
            "model_sha256": model.sha256, "coverage": metrics, "observation": observed,
            "classes": len(proof["blocks"]), "positive_classes": len(proof["blocks"])-1,
            "derived_observations": len(proof["predicates"]), "completion": COMPLETION,
            "all_positive_widths_in_declared_profile": True, "target_checked": False, "lean_checked": False}


def explain(source, selection, certificate):
    checked = check_observations(source, selection, certificate)
    bridge = certificate["source_model"]
    return {"result": checked, "interpretation": "guards establish equality mismatch for every remaining suffix; "
            "unused coordinates are removed by exact dependency closure, not representative sampling",
            "reductions": bridge["reduction"]["steps"],
            "erasures": [{"from": e["state"], "symbol": e["symbol"], "to": e["next"], **e["proof"]}
                         for e in bridge["edges"] if e["proof"]["retired_equalities"]
                         or e["proof"]["dropped"]["nodes"]]}
