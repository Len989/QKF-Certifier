"""Discover a finite product after source-independent observation inference."""
from copy import deepcopy

from research.signed_observations.producer import derive
from research.signed_runtime.runtime import load
from research.wordexpr.frontend import Unsupported
from .common import Monitor, SCHEMA, binding, budgets as validate_budgets, prepare
from .checker import check


class ProductLimit(ValueError):
    """Incomplete search is neither a proof nor a program refutation."""


def discover(monitor, max_states, max_witness):
    states, parents, ids = [monitor.initial], [None], {monitor.initial: 0}
    for i, state in enumerate(states):
        for symbol in monitor.alphabet:
            following = monitor.step(state, symbol)
            if monitor.bad(following):
                word, cursor = [symbol], i
                while parents[cursor] is not None:
                    cursor, previous = parents[cursor]
                    word.append(previous)
                if len(word) > max_witness:
                    raise ProductLimit("target counterexample length budget")
                return {"kind": "counterexample", "word": list(reversed(word))}
            if following not in ids:
                if len(states) >= max_states:
                    raise ProductLimit("target product state budget")
                ids[following] = len(states)
                states.append(following)
                parents.append([i, symbol])
    return {"kind": "closure", "states": [{"state": list(s), "parent": p}
            for s, p in zip(states, parents)]}


def prove(source, target, *, budgets=None):
    target = deepcopy(target)
    compiled, selection = prepare(target)
    ceilings = validate_budgets(budgets)
    try:
        observation, status = derive(source, selection, **{
            k: ceilings[k] for k in ("max_states", "max_observations", "max_pullbacks", "max_classes")})
    except Unsupported as exc:
        return None, {"status": "unsupported", "stage": "source_profile", "reason": str(exc),
                      "source_interface_verified": False, "target_checked": False}
    if observation is None:
        return None, {**status, "source_interface_verified": False}
    runner, receipt = load(source, selection, observation)
    monitor = Monitor(runner, compiled["specification"])
    try:
        obligation = discover(monitor, ceilings["max_target_states"], ceilings["max_witness_bits"])
    except ProductLimit as exc:
        return None, {"status": "budget_exhausted", "stage": "target_product", "reason": str(exc),
                      "source_interface_verified": True, "target_checked": False,
                      "runtime": receipt}
    certificate = {"schema": SCHEMA, "binding": binding(compiled, receipt),
                   "observations": observation, "obligation": obligation}
    # A producer can propose a candidate, but only independent replay returns
    # the accepted target verdict. Timing/search metadata is not a proof premise.
    return certificate, check(source, target, certificate)
