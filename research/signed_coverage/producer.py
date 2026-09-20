"""Discover only live residual descriptions; emit replayable erasure obligations."""
from copy import deepcopy
from research.observations.model import MODEL_SCHEMA as FINITE_SCHEMA, Model, digest, integer, require
from research.signed_reduction.producer import derive, ReductionLimit
from research.signed_reduction.checker import rebuild as replay_reduction
from research.signed_reduction.rules import rhs, rewrite
from research.wordexpr.frontend import Unsupported
from .local import (ALPHABET, BOOL_RULES, ENGINE, LAW, MAX_STATES, MAX_TOTAL_STEPS, MAX_EDGE_STEPS,
                    MODEL_SCHEMA, OBS_SCHEMA, binding, derivative, finish, initial, terminal)
from .checker import check_model, check_observations


class CoverageLimit(ValueError):
    def __init__(self, reason, counts):
        super().__init__(reason)
        self.counts = dict(counts)


def first(ir, term, path=()):
    if term[0] not in {"atom", "literal"}:
        for i, child in enumerate(term[1:], 1):
            found = first(ir, child, (*path, i))
            if found is not None:
                return found
    for rule in BOOL_RULES:
        if rhs(ir, term, rule) is not None:
            return {"path": list(path), "rule": rule}
    return None


def edge_candidate(ir, state, symbol, available):
    following, guards, formula = derivative(ir, state, symbol)
    steps = []
    while True:
        instruction = first(ir, formula)
        if instruction is None:
            break
        if len(steps) >= min(available, MAX_EDGE_STEPS):
            raise CoverageLimit("guarded local rewrite budget", {"local_steps_in_failed_edge": len(steps)})
        formula = rewrite(ir, formula, instruction)
        steps.append(instruction)
    next_state, dropped = finish(ir, state, following, formula)
    return next_state, {"law": LAW, "retired_equalities": guards, "steps": steps, "dropped": dropped}


def build(source, selection, *, max_states=64, max_steps=512, max_local_steps=4096):
    require(integer(max_states, 1, MAX_STATES) and integer(max_steps, 0, 512)
            and integer(max_local_steps, 0, MAX_TOTAL_STEPS), "guarded construction budgets")
    reduction, _ = derive(source, selection, max_steps=max_steps)
    _, ir = replay_reduction(source, selection, reduction)
    states, parents, edges = [initial(ir)], [None], []
    ids, counts = {digest(states[0]): 0}, {"created_states": 1, "completed_branches": 0,
                                         "local_rewrite_steps": 0, "original_states_enumerated": 0}
    for i, state in enumerate(states):
        for symbol in ALPHABET:
            try:
                following, proof = edge_candidate(ir, state, symbol,
                                                  max_local_steps-counts["local_rewrite_steps"])
            except CoverageLimit as exc:
                raise CoverageLimit(str(exc), {**counts, **exc.counts}) from exc
            key = digest(following)
            counts["local_rewrite_steps"] += len(proof["steps"])
            if key not in ids:
                if len(states) >= max_states:
                    raise CoverageLimit("covered state budget; unexplored sector is not certified", counts)
                ids[key] = len(states)
                states.append(following)
                parents.append([i, symbol])
                counts["created_states"] += 1
            edges.append({"state": i, "symbol": symbol, "next": ids[key], "proof": proof})
            counts["completed_branches"] += 1
    bound = binding(selection, reduction, ir)
    names = ["g%03d" % i for i in range(len(states))]
    model = Model({"schema": FINITE_SCHEMA, "states": names, "alphabet": list(ALPHABET),
                   "outputs": ["_"], "initial": names[0],
                   "terminal": {n: terminal(ir, s) for n, s in zip(names, states)},
                   "steps": [{"state": names[e["state"]], "symbol": e["symbol"], "output": "_",
                              "next": names[e["next"]]} for e in edges], "binding": bound})
    certificate = {"schema": MODEL_SCHEMA, "binding": bound, "reduction": reduction,
                   "states": states, "parents": parents, "edges": edges, "model": model.data}
    return certificate, check_model(source, selection, certificate)


def infer(source, selection, *, max_states=64, max_steps=512, max_local_steps=4096,
          max_observations=63, max_pullbacks=4096, max_classes=64):
    from research.observations.producer import synthesize
    require(integer(max_observations, 0, 63) and integer(max_pullbacks, 0, 100000)
            and integer(max_classes, 1, 64), "observation resource ceilings")
    try:
        model, _ = build(source, selection, max_states=max_states, max_steps=max_steps,
                         max_local_steps=max_local_steps)
    except Unsupported as exc:
        return None, {"status": "unsupported", "stage": "source_profile", "reason": str(exc)}
    except ReductionLimit as exc:
        return None, {"status": "budget_exhausted", "stage": "source_reduction", "reason": str(exc)}
    except CoverageLimit as exc:
        return None, {"status": "budget_exhausted", "stage": "guarded_coverage", "reason": str(exc),
                      "attempt": exc.counts}
    proposed = synthesize(model["model"], row_encoding="atomic", max_observations=max_observations,
                          max_pullbacks=max_pullbacks, max_classes=max_classes)
    if proposed["status"] == "budget_exhausted":
        return None, {"status": "budget_exhausted", "stage": "observation_closure", "reason": proposed["reason"]}
    require(proposed["status"] == "candidate", "generic observation candidate")
    certificate = {"schema": OBS_SCHEMA, "source_model": model, "observations": proposed["certificate"]}
    return certificate, check_observations(source, selection, certificate)
