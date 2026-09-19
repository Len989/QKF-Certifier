"""Low-to-high modular semantics with terminal signed-order atoms."""

from research.observations.model import MODEL_SCHEMA, Model, integer, require
from research.wordexpr import semantics as words


def initial(ir):
    return (*words.initial(ir), *(0 for _ in range(2 * len(ir["atoms"]))))


def valid_state(ir, state):
    n = len(ir["nodes"])
    require(type(state) in {tuple, list} and len(state) == n + 2 * len(ir["atoms"]),
            "signed predicate residual vector")
    words.valid_state(ir, state[:n])
    require(all(integer(x, 0, 1) for x in state[n:]), "signed predicate atom residuals")
    return tuple(state)


def _bit(ir, arithmetic, node, symbol):
    return int(words.cell({**ir, "root": node}, arithmetic, symbol)[0])


def cell(ir, state, symbol):
    n = len(ir["nodes"])
    arithmetic = state[:n]
    _, following = words.cell({**ir, "root": 0}, arithmetic, symbol)
    atom_state = []
    old = state[n:]
    for index, atom in enumerate(ir["atoms"]):
        a, b = old[2 * index:2 * index + 2]
        if atom["kind"] == "eq":
            left = _bit(ir, arithmetic, atom["left"], symbol)
            right = _bit(ir, arithmetic, atom["right"], symbol)
            atom_state.extend((int(bool(a or left != right)), 0))
        else:
            require(atom["kind"] == "signed_zero", "known signed predicate atom")
            bit = _bit(ir, arithmetic, atom["node"], symbol)
            atom_state.extend((int(bool(a or bit)), bit))
    return (*following, *atom_state)


def atom_value(atom, state):
    nonzero_or_difference, sign = state
    if atom["kind"] == "eq":
        return nonzero_or_difference == 0
    op = atom["op"]
    nonzero = bool(nonzero_or_difference)
    if op == ">":
        return nonzero and sign == 0
    if op == ">=":
        return sign == 0
    if op == "<":
        return sign == 1
    if op == "<=":
        return sign == 1 or not nonzero
    raise ValueError("unknown signed comparison")


def formula_value(term, atoms):
    op = term[0]
    if op == "atom":
        return atoms[term[1]]
    if op == "literal":
        return term[1]
    if op == "not":
        return not formula_value(term[1], atoms)
    if op == "and":
        return formula_value(term[1], atoms) and formula_value(term[2], atoms)
    if op == "or":
        return formula_value(term[1], atoms) or formula_value(term[2], atoms)
    if op == "xor":
        return formula_value(term[1], atoms) != formula_value(term[2], atoms)
    raise ValueError("unknown signed Boolean formula")


def terminal(ir, state):
    n = len(ir["nodes"])
    values = [
        atom_value(atom, state[n + 2 * i:n + 2 * i + 2])
        for i, atom in enumerate(ir["atoms"])
    ]
    return formula_value(ir["formula"], values)


def _signed(value, width):
    sign = 1 << (width - 1)
    return value - (1 << width) if value & sign else value


def evaluate(ir, x, width):
    require(integer(width, 1, 4096) and integer(x, 0, (1 << width) - 1),
            "signed predicate input")
    values = [
        words.evaluate({**ir, "root": i}, x, width)
        for i in range(len(ir["nodes"]))
    ]
    atoms = []
    for atom in ir["atoms"]:
        if atom["kind"] == "eq":
            atoms.append(values[atom["left"]] == values[atom["right"]])
        else:
            value = _signed(values[atom["node"]], width)
            atoms.append({
                ">": value > 0,
                ">=": value >= 0,
                "<": value < 0,
                "<=": value <= 0,
            }[atom["op"]])
    return formula_value(ir["formula"], atoms)


def model(ir, states):
    names = {state: "s" + str(i) for i, state in enumerate(states)}
    rows = []
    for state in states:
        for symbol in ("0", "1"):
            following = cell(ir, state, symbol)
            require(following in names, "signed predicate source closure")
            rows.append({
                "state": names[state],
                "symbol": symbol,
                "output": "_",
                "next": names[following],
            })
    return Model({
        "schema": MODEL_SCHEMA,
        "states": list(names.values()),
        "alphabet": ["0", "1"],
        "outputs": ["_"],
        "initial": names[initial(ir)],
        "terminal": {
            names[state]: str(bool(terminal(ir, state))).lower()
            for state in states
        },
        "steps": rows,
        "binding": {"source_ir": ir},
    }).data
