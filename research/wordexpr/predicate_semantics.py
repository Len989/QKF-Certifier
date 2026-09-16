"""Reuse word cut rules; accumulate inequality bits and observe only at end."""
from research.observations.model import MODEL_SCHEMA, Model, integer, require
from . import semantics as words


def initial(ir):
    return (*words.initial(ir), *(0 for _ in ir['atoms']))


def valid_state(ir, state):
    n = len(ir['nodes'])
    require(type(state) in {tuple, list} and len(state) == n + len(ir['atoms']), 'predicate residual vector')
    words.valid_state(ir, state[:n])
    require(all(integer(s, 0, 1) for s in state[n:]), 'typed inequality flags')
    return tuple(state)


def cell(ir, state, symbol):
    n = len(ir['nodes'])
    arithmetic = state[:n]
    # Even unused arithmetic nodes are interpreted. Atoms share their state.
    _, following = words.cell({**ir, 'root': 0}, arithmetic, symbol)
    differences = []
    for old, (a, b) in zip(state[n:], ir['atoms']):
        left = words.cell({**ir, 'root': a}, arithmetic, symbol)[0]
        right = words.cell({**ir, 'root': b}, arithmetic, symbol)[0]
        differences.append(int(bool(old or left != right)))
    return (*following, *differences)


def formula_value(t, equalities):
    op = t[0]
    if op == 'atom': return equalities[t[1]]
    if op == 'literal': return t[1]
    if op == 'not': return not formula_value(t[1], equalities)
    if op == 'and': return formula_value(t[1], equalities) and formula_value(t[2], equalities)
    if op == 'or': return formula_value(t[1], equalities) or formula_value(t[2], equalities)
    raise ValueError('unknown Boolean formula')


def terminal(ir, state):
    return formula_value(ir['formula'], [s == 0 for s in state[len(ir['nodes']):]])


def evaluate(ir, x, width):
    # Independent whole-word interpretation, not bit transitions.
    eq = [words.evaluate({**ir, 'root': a}, x, width) ==
          words.evaluate({**ir, 'root': b}, x, width) for a, b in ir['atoms']]
    # Validate input even for a constant Boolean result with no atoms.
    words.evaluate({**ir, 'root': 0}, x, width)
    return formula_value(ir['formula'], eq)


def model(ir, states):
    names = {s: 's' + str(i) for i, s in enumerate(states)}
    rows = []
    for s in states:
        for a in ('0', '1'):
            nxt = cell(ir, s, a)
            require(nxt in names, 'predicate source closure')
            rows.append({'state': names[s], 'symbol': a, 'output': '_', 'next': names[nxt]})
    return Model({'schema': MODEL_SCHEMA, 'states': list(names.values()), 'alphabet': ['0', '1'],
                  'outputs': ['_'], 'initial': names[initial(ir)],
                  'terminal': {name: str(terminal(ir, s)).lower() for s, name in names.items()},
                  'steps': rows, 'binding': {'source_ir': ir}}).data
