"""Counterexample-guided richer observation inference and direct target closure."""

from research.observations.model import integer, require
from research.inference.adapters import blocks_for, conflict
from research.inference.producer import InferenceFailure

from .v3_adapters import System
from .v3_checker import SCHEMA, check


def _feature_for(system, selected, issue):
    left, right = tuple(issue["left"]), tuple(issue["right"])
    for feature in system.features:
        fid = feature["id"]
        if fid in selected:
            continue
        if system.feature_value(fid, left) != system.feature_value(fid, right):
            return fid
    raise InferenceFailure("v3 candidate library cannot separate behavioral conflict")


def _word(parents, cursor, symbol):
    result = [symbol]
    while parents[cursor] is not None:
        cursor, previous = parents[cursor]
        result.append(previous)
    result.reverse()
    return result


def _target_proof(system, selected, max_states):
    if system.family != "signed-terminal-predicate":
        from .v2_producer import _target_proof as legacy_target_proof
        return legacy_target_proof(system, selected, max_states)
    from .v3_target_checker import MAX_WITNESS, SignedTarget
    monitor = SignedTarget(system, selected)
    states, parents, ids = [monitor.initial], [None], {monitor.initial: 0}
    for i, state in enumerate(states):
        for symbol in monitor.alphabet:
            following = monitor.transition(state, symbol)
            if monitor.bad(following):
                word = _word(parents, i, symbol)
                if len(word) > MAX_WITNESS:
                    raise InferenceFailure("v3 signed target witness budget")
                return {"kind": "counterexample", "word": word}
            if following not in ids:
                if len(states) == max_states:
                    raise InferenceFailure("v3 signed target product budget")
                ids[following] = len(states)
                states.append(following)
                parents.append([i, symbol])
    return {"kind": "closure", "states": [
        {"state": list(state), "parent": parent}
        for state, parent in zip(states, parents)
    ]}


def infer(source, target, *, max_features=128, max_target_states=8192):
    require(integer(max_features, 0, 256), "v3 inference feature budget")
    require(integer(max_target_states, 1, 8192), "v3 target product budget")
    system = System(source, target)
    selected, refinements = [], []

    while True:
        issue = conflict(system, selected)
        if issue is None:
            break
        if len(selected) == max_features:
            raise InferenceFailure("v3 observation feature budget")
        fid = _feature_for(system, selected, issue)
        refinements.append({"feature": fid, "conflict": issue})
        selected.append(fid)

    # Restart after each deletion.  Stability is not assumed monotone under
    # arbitrary coarsening, so a single pass need not be deletion-irredundant.
    pruning = []
    while True:
        removed = False
        for fid in reversed(list(selected)):
            trial = [x for x in selected if x != fid]
            issue = conflict(system, trial)
            if issue is None:
                pruning.append({"feature": fid, "removed": True})
                selected = trial
                removed = True
                break
            pruning.append({"feature": fid, "removed": False, "conflict": issue})
        if not removed:
            break

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
