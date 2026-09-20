"""Typed local Boolean equalities; no normalization search or target premises.

Word DAG/atom sharing already exists in the signed frontend. This layer adds
Boolean equality replay and a checked live-dependency projection. It does not
import the unrelated KnownBits/MLIR rewrite rules or assume Java partiality away:
the complete source is first admitted by the retained pure, total signed profile.
"""
from copy import deepcopy
from research.observations.model import digest, integer, require

SCHEMA = "qkf-signed-source-reduction-v1"
RULESET = "typed-signed-boolean-reduction-v1"
MAX_STEPS = 512
RULES = ("atom-alias", "eq-reflexive", "signed-zero", "not-literal",
         "double-not", "bool-literal", "idempotent", "complement", "absorption")
LEAVES = {"atom", "literal"}


def validate_formula(term, atoms):
    count = 0
    def visit(t, depth):
        nonlocal count
        count += 1
        require(depth < 32 and count <= 192 and type(t) is list and t,
                "bounded typed Boolean formula")
        op = t[0]
        require(type(op) is str, "Boolean operation identifier")
        if op == "literal":
            require(len(t) == 2 and type(t[1]) is bool, "Boolean literal, not integer")
        elif op == "atom":
            require(len(t) == 2 and integer(t[1], 0, atoms - 1), "Boolean atom reference")
        else:
            arity = 1 if op == "not" else 2 if op in {"and", "or", "xor"} else -1
            require(len(t) == arity + 1, "Boolean operator/arity")
            for child in t[1:]:
                visit(child, depth + 1)
    visit(term, 0)
    return count


def atom_key(row):
    if row["kind"] == "eq":
        return "eq", *sorted((row["left"], row["right"]))
    return "signed_zero", row["node"], row["op"]


def rhs(ir, term, rule):
    """Return the one prescribed replacement, or None when inapplicable.

The atom alias rule only uses identical native atoms or symmetry of word
*equality*. No signed-order relation or nonzero literal is constant-folded.
"""
    op = term[0]
    if op == "atom":
        index = term[1]
        atom = ir["atoms"][index]
        if rule == "atom-alias":
            key = atom_key(atom)
            for j in range(index):
                if atom_key(ir["atoms"][j]) == key:
                    return ["atom", j]
        if rule == "eq-reflexive" and atom["kind"] == "eq" and atom["left"] == atom["right"]:
            return ["literal", True]
        if (rule == "signed-zero" and atom["kind"] == "signed_zero"
                and ir["nodes"][atom["node"]] == ["const", 0]):
            return ["literal", atom["op"] in {">=", "<="}]
        return None
    if op == "not":
        a = term[1]
        if rule == "not-literal" and a[0] == "literal":
            return ["literal", not a[1]]
        if rule == "double-not" and a[0] == "not":
            return deepcopy(a[1])
    if op not in {"and", "or", "xor"}:
        return None
    a, b = term[1:]
    if rule == "bool-literal":
        if a[0] == b[0] == "literal":
            x, y = a[1], b[1]
            return ["literal", x and y if op == "and" else x or y if op == "or" else x != y]
        for literal, other in ((a, b), (b, a)):
            if literal[0] == "literal":
                value = literal[1]
                if op == "and":
                    return deepcopy(other) if value else ["literal", False]
                if op == "or":
                    return ["literal", True] if value else deepcopy(other)
                return ["not", deepcopy(other)] if value else deepcopy(other)
    if rule == "idempotent" and a == b:
        return ["literal", False] if op == "xor" else deepcopy(a)
    if rule == "complement" and (a == ["not", b] or b == ["not", a]):
        return ["literal", op != "and"]
    if rule == "absorption" and op in {"and", "or"}:
        dual = "or" if op == "and" else "and"
        for outer, nested in ((a, b), (b, a)):
            if nested[0] == dual and outer in nested[1:]:
                return deepcopy(outer)
    return None


def rewrite(ir, formula, instruction):
    require(type(instruction) is dict and set(instruction) == {"path", "rule"},
            "reduction instruction fields")
    path, rule = instruction["path"], instruction["rule"]
    require(type(path) is list and len(path) < 32 and type(rule) is str and rule in RULES,
            "reduction path and declared rule")
    result = deepcopy(formula)
    cursor = result
    for index in path:
        require(cursor[0] not in LEAVES and integer(index, 1, len(cursor) - 1),
                "path must select a Boolean child, not a payload")
        cursor = cursor[index]
    replacement = rhs(ir, cursor, rule)
    require(replacement is not None, "inapplicable Boolean rule: " + rule)
    if path:
        parent = result
        for index in path[:-1]:
            parent = parent[index]
        parent[path[-1]] = replacement
    else:
        result = replacement
    validate_formula(result, len(ir["atoms"]))
    return result


def compact(ir, formula):
    """Exact dependency slice, checked again on replay; never enumerate states.

Maps are new index -> old index in increasing dependency order. Node zero is
always the existing input anchor: retained bit semantics expects a nonempty
arithmetic vector even for a constant formula. It has no mutable carry.
"""
    validate_formula(formula, len(ir["atoms"]))
    used_atoms = set()
    def atoms(t):
        if t[0] == "atom":
            used_atoms.add(t[1])
        elif t[0] != "literal":
            for child in t[1:]:
                atoms(child)
    atoms(formula)
    require(ir["nodes"][0] == ["input"], "retained input anchor")
    used_nodes = {0}
    def nodes(index):
        if index in used_nodes:
            return
        used_nodes.add(index)
        row = ir["nodes"][index]
        if row[0] not in {"input", "const"}:
            for arg in row[1:]:
                nodes(arg)
    for index in used_atoms:
        a = ir["atoms"][index]
        for name in (("left", "right") if a["kind"] == "eq" else ("node",)):
            nodes(a[name])
    node_map, atom_map = sorted(used_nodes), sorted(used_atoms)
    ni, ai = {v: i for i, v in enumerate(node_map)}, {v: i for i, v in enumerate(atom_map)}
    reduced_nodes = []
    for index in node_map:
        row = ir["nodes"][index]
        reduced_nodes.append(deepcopy(row) if row[0] in {"input", "const"}
                             else [row[0], *(ni[arg] for arg in row[1:])])
    reduced_atoms = []
    for index in atom_map:
        a = deepcopy(ir["atoms"][index])
        for name in (("left", "right") if a["kind"] == "eq" else ("node",)):
            a[name] = ni[a[name]]
        reduced_atoms.append(a)
    def remap(t):
        if t[0] == "atom":
            return ["atom", ai[t[1]]]
        if t[0] == "literal":
            return deepcopy(t)
        return [t[0], *(remap(child) for child in t[1:])]
    reduced = {**deepcopy(ir), "nodes": reduced_nodes, "atoms": reduced_atoms,
               "formula": remap(formula)}
    return reduced, {"nodes": node_map, "atoms": atom_map}


def binding(selection, ir):
    return {"source_sha256": ir["source_sha256"], "request_sha256": digest(selection),
            "original_ir_sha256": digest(ir), "contract": ir["contract"], "ruleset": RULESET}
