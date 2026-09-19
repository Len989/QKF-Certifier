"""Counterexample-guided richer observation inference and direct target closure."""

from research.observations.model import integer, require
from research.inference.adapters import blocks_for, conflict
from research.inference.producer import InferenceFailure, _target_proof as v1_target_proof

from .v2_adapters import System
from .v2_checker import SCHEMA, check
from .v2_target_checker import AscendingTarget


def _feature_for(system, selected, issue):
    left, right = tuple(issue["left"]), tuple(issue["right"])
    for feature in system.features:
        fid = feature["id"]
        if fid in selected:
            continue
        if system.feature_value(fid, left) != system.feature_value(fid, right):
            return fid
    raise InferenceFailure("v2 candidate library cannot separate behavioral conflict")


def _word(parents, cursor, symbol):
    result = [symbol]
    while parents[cursor] is not None:
        cursor, previous = parents[cursor]
        result.append(previous)
    result.reverse()
    return result


def _ascending_target_proof(system, selected, max_states):
    monitor = AscendingTarget(system, selected)
    states, parents, ids = [monitor.initial], [None], {monitor.initial: 0}
    for i, state in enumerate(states):
        for column in monitor.alphabet:
            following, _env, _output = monitor.transition(state, column)
            reason = monitor.bad(following)
            if reason is not None:
                word = _word(parents, i, column)
                final, values = monitor.trace(word)
                require(monitor.bad(final) == reason, "stable v2 successor witness")
                return {
                    "kind": "counterexample",
                    "word": word,
                    "reason": reason,
                    "values": values,
                }
            if following not in ids:
                if len(states) == max_states:
                    raise InferenceFailure("v2 successor target product budget")
                ids[following] = len(states)
                states.append(following)
                parents.append([i, column])
    return {
        "kind": "closure",
        "states": [
            {"state": list(state), "parent": parent}
            for state, parent in zip(states, parents)
        ],
    }


def _target_proof(system, selected, max_states):
    if system.family == "ascending-region":
        return _ascending_target_proof(system, selected, max_states)
    return v1_target_proof(system, selected, max_states=min(max_states, 4096))


def infer(source, target, *, max_features=128, max_target_states=8192):
    require(integer(max_features, 0, 256), "v2 inference feature budget")
    require(integer(max_target_states, 1, 8192), "v2 target product budget")
    system = System(source, target)
    selected, refinements = [], []

    while True:
        issue = conflict(system, selected)
        if issue is None:
            break
        if len(selected) == max_features:
            raise InferenceFailure("v2 observation feature budget")
        fid = _feature_for(system, selected, issue)
        refinements.append({"feature": fid, "conflict": issue})
        selected.append(fid)

    greedy = list(selected)
    pruning = []
    for fid in reversed(greedy):
        if fid not in selected:
            continue
        trial = [x for x in selected if x != fid]
        issue = conflict(system, trial)
        if issue is None:
            pruning.append({"feature": fid, "removed": True})
            selected = trial
        else:
            pruning.append({"feature": fid, "removed": False, "conflict": issue})

    blocks, _block_of = blocks_for(system, selected)
    certificate = {
        "schema": SCHEMA,
        "binding": system.binding,
        "refinements": refinements,
        "pruning": pruning,
        "selected": selected,
        "blocks": [[list(s) for s in block] for block in blocks],
        "target_proof": _target_proof(system, selected, max_target_states),
    }
    return certificate, check(source, target, certificate)
