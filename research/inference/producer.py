"""Counterexample-guided selection of source-derived residual observations."""

from research.observations.model import digest, integer, require

from .adapters import System, blocks_for, conflict, quotient_cells
from .checker import SCHEMA, check


class InferenceFailure(ValueError):
    pass


def _feature_for(system, selected, issue):
    left, right = tuple(issue["left"]), tuple(issue["right"])
    for feature in system.features:
        fid = feature["id"]
        if fid in selected:
            continue
        if system.feature_value(fid, left) != system.feature_value(fid, right):
            return fid
    raise InferenceFailure("candidate library cannot separate behavioral conflict")


def _word(states, parents, cursor, symbol):
    result = [symbol]
    while parents[cursor] is not None:
        cursor, previous = parents[cursor]
        result.append(previous)
    result.reverse()
    return result


def _target_proof(system, selected, *, max_states=4096):
    require(integer(max_states, 1, 4096), "target inference product budget")
    blocks, block_of, cells = quotient_cells(system, selected)
    table = {(r["state"], r["symbol"]): (r["output"], r["next"]) for r in cells}

    if system.family == "ascending-region":
        return {
            "kind": "interface_only",
            "reason": "successor_target_checker_not_connected_v1",
        }

    if system.family == "streaming-word":
        from research.wordexpr import semantics as sem

        target = system.target_data["ir"]
        first = (block_of[system.initial], sem.goal_initial(target))
        states, parents, ids = [first], [None], {first: 0}
        for i, (q, t) in enumerate(states):
            for symbol in system.alphabet:
                actual, nq = table[q, symbol]
                expected, nt = sem.goal_cell(target, t, symbol)
                if actual != expected:
                    return {"kind": "counterexample", "word": _word(states, parents, i, symbol)}
                following = (nq, nt)
                if following not in ids:
                    if len(states) == max_states:
                        raise InferenceFailure("word target product budget")
                    ids[following] = len(states)
                    states.append(following)
                    parents.append([i, symbol])
        return {
            "kind": "closure",
            "states": [
                {"state": [q, list(t)], "parent": parent}
                for (q, t), parent in zip(states, parents)
            ],
        }

    from research.wordexpr.predicate_frontend import target_value

    limit = system.target_data["limit"]
    target = system.target_data["spec"]["target"]
    first = (block_of[system.initial], 0, False)
    states, parents, ids = [first], [None], {first: 0}
    for i, (q, count, started) in enumerate(states):
        for symbol in system.alphabet:
            _, nq = table[q, symbol]
            nc = min(limit, count + int(symbol))
            following = (nq, nc, True)
            source_terminal = system.terminal(blocks[nq][0])
            expected = str(bool(target_value(target, nc))).lower()
            if source_terminal != expected:
                return {"kind": "counterexample", "word": _word(states, parents, i, symbol)}
            if following not in ids:
                if len(states) == max_states:
                    raise InferenceFailure("predicate target product budget")
                ids[following] = len(states)
                states.append(following)
                parents.append([i, symbol])
    return {
        "kind": "closure",
        "states": [
            {"state": [q, count, started], "parent": parent}
            for (q, count, started), parent in zip(states, parents)
        ],
    }


def infer(source, target, *, max_features=64, max_target_states=4096):
    """Infer a stable quotient from the finite residual feature library."""
    require(integer(max_features, 0, 128), "inference feature budget")
    system = System(source, target)
    selected, refinements = [], []

    while True:
        issue = conflict(system, selected)
        if issue is None:
            break
        if len(selected) == max_features:
            raise InferenceFailure("observation feature budget")
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
        "target_proof": _target_proof(system, selected, max_states=max_target_states),
    }
    return certificate, check(source, target, certificate)
