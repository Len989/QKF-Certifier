"""Bounded local simplification; emits rules/paths, never a trusted reduced IR."""
from copy import deepcopy
from research.observations.model import integer, require
from research.signed_bridge.model import CapacityExceeded, read
from .rules import LEAVES, MAX_STEPS, RULES, SCHEMA, binding, compact, rhs, rewrite


class ReductionLimit(CapacityExceeded):
    """A trace budget is exhausted; no partially simplified certificate returned."""


def first(ir, term, path=()):
    if term[0] not in LEAVES:
        for index, child in enumerate(term[1:], 1):
            found = first(ir, child, (*path, index))
            if found is not None:
                return found
    for rule in RULES:
        if rhs(ir, term, rule) is not None:
            return {"path": list(path), "rule": rule}
    return None


def derive(source, selection, *, max_steps=MAX_STEPS):
    require(integer(max_steps, 0, MAX_STEPS), "reduction budget must be 0..512")
    ir = read(source, selection)
    formula, steps = deepcopy(ir["formula"]), []
    while True:
        instruction = first(ir, formula)
        if instruction is None:
            break
        if len(steps) >= max_steps:
            raise ReductionLimit("Boolean reduction step budget")
        formula = rewrite(ir, formula, instruction)
        steps.append(instruction)
    reduced, projection = compact(ir, formula)
    certificate = {"schema": SCHEMA, "binding": binding(selection, ir), "original_ir": ir,
                   "steps": steps, "final_formula": formula, "projection": projection,
                   "reduced_ir": reduced}
    from .checker import check
    return certificate, check(source, selection, certificate)
