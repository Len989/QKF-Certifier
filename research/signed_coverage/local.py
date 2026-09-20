"""Local residual-continuation equalities; no carrier enumeration or search.

A state denotes a formula and exactly its live residual coordinates. Other
coordinates are universally irrelevant by dependency closure, not sampled or
assigned a default. An equality's accumulated mismatch is absorbing under OR;
only that guard permits replacing the atom by false for ALL future suffixes.
Pure Boolean replay and exact projection then change the residual description.
"""
from copy import deepcopy
from research.observations.model import digest, integer, require
from research.signed_predicates import semantics as native
from research.signed_reduction.rules import compact, rewrite, validate_formula
from research.signed_bridge.model import COMPLETION, EMPTY

MODEL_SCHEMA = "qkf-signed-guarded-source-model-v1"
OBS_SCHEMA = "qkf-signed-guarded-observations-v1"
ENGINE = "signed-guarded-residual-coverage-v1"
LAW = "absorbing-equality-mismatch-and-live-projection-v1"
# Native atom identities are NOT unconditional identities at an arbitrary cut.
# Only propositional rules are reused after a word prefix has been consumed.
BOOL_RULES = ("not-literal", "double-not", "bool-literal", "idempotent", "complement", "absorption")
MAX_STATES, MAX_EDGE_STEPS, MAX_TOTAL_STEPS = 64, 512, 4096
ALPHABET = ("0", "1")


def binding(selection, reduction, ir):
    return {"source_sha256": ir["source_sha256"], "request_sha256": digest(selection),
            "reduction_sha256": digest(reduction), "reduced_ir_sha256": digest(ir),
            "contract": selection["contract"], "completion": COMPLETION,
            "engine": ENGINE, "local_law": LAW}


def view(ir, state):
    require(type(state) is dict and set(state) == {"has_bits", "formula", "projection", "residual"},
            "guarded residual state fields")
    require(type(state["has_bits"]) is bool and type(state["residual"]) is list,
            "typed completion and residual")
    validate_formula(state["formula"], len(ir["atoms"]))
    sliced, projection = compact(ir, state["formula"])
    require(digest(projection) == digest(state["projection"]), "exact live dependency closure")
    residual = native.valid_state(sliced, state["residual"])
    return sliced, projection, residual


def initial(ir):
    sliced, projection = compact(ir, ir["formula"])
    return {"has_bits": False, "formula": deepcopy(ir["formula"]),
            "projection": projection, "residual": list(native.initial(sliced))}


def terminal(ir, state):
    sliced, _, residual = view(ir, state)
    return str(bool(native.terminal(sliced, residual))).lower() if state["has_bits"] else EMPTY


def substitute_false(formula, indices):
    if formula[0] == "atom":
        return ["literal", False] if formula[1] in indices else deepcopy(formula)
    if formula[0] == "literal":
        return deepcopy(formula)
    return [formula[0], *(substitute_false(c, indices) for c in formula[1:])]


def derivative(ir, state, symbol):
    """Exact step on live coordinates; no values chosen for omitted coordinates.

Dependency closure proves this calculation commutes with every completion of
those omitted coordinates for this formula. The returned guard is exact: no
signed-zero atom, merely currently false atom, or failed sample is retired.
"""
    require(type(symbol) is str and symbol in ALPHABET, "complete binary input branch")
    sliced, projection, residual = view(ir, state)
    following = native.valid_state(sliced, native.cell(sliced, residual, symbol))
    n = len(sliced["nodes"])
    guards = [index for j, index in enumerate(projection["atoms"])
              if sliced["atoms"][j]["kind"] == "eq" and following[n + 2 * j] == 1]
    specialized = substitute_false(state["formula"], set(guards))
    return following, guards, specialized


def finish(ir, state, following, formula):
    """Transport retained coordinates; require subset dependency projection."""
    _, before, _ = view(ir, state)
    sliced, after = compact(ir, formula)
    require(set(after["nodes"]) <= set(before["nodes"])
            and set(after["atoms"]) <= set(before["atoms"]), "no forgotten dependency resurrected")
    n = len(before["nodes"])
    words = dict(zip(before["nodes"], following[:n]))
    atoms = {a: following[n + 2*j:n + 2*j + 2] for j, a in enumerate(before["atoms"])}
    residual = [words[i] for i in after["nodes"]]
    for i in after["atoms"]:
        residual.extend(atoms[i])
    native.valid_state(sliced, residual)
    dropped = {key: sorted(set(before[key]) - set(after[key])) for key in ("nodes", "atoms")}
    return {"has_bits": True, "formula": deepcopy(formula),
            "projection": after, "residual": residual}, dropped


def replay_edge(ir, state, symbol, proof):
    require(type(proof) is dict and set(proof) == {"law", "retired_equalities", "steps", "dropped"}
            and proof["law"] == LAW, "local coverage proof fields/law")
    following, guards, formula = derivative(ir, state, symbol)
    require(digest(proof["retired_equalities"]) == digest(guards),
            "missing or false absorbing mismatch guard")
    steps = proof["steps"]
    require(type(steps) is list and len(steps) <= MAX_EDGE_STEPS, "bounded local Boolean proof")
    for instruction in steps:
        require(type(instruction) is dict and instruction.get("rule") in BOOL_RULES,
                "only propositional equalities valid at arbitrary residual cuts")
        formula = rewrite(ir, formula, instruction)
    following_state, dropped = finish(ir, state, following, formula)
    require(digest(dropped) == digest(proof["dropped"]), "exact discarded dependency list")
    return following_state
