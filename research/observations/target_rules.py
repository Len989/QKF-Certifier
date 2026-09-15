"""Exact bit observations and an independent whole-integer target interpretation.

Word/formula syntax is validated by target_syntax. No source-specific transition
or target-name-specific monitor lives here. The integer evaluator does not use
the compiled observation program or its step functions.
"""
from itertools import product

from .model import integer, require
from .target_syntax import (COLUMN_NAMES, DOMAINS, MAX_ATOMS, MAX_DEPTH, MAX_NODES,
                            RULES, SPEC_SCHEMA, compile_spec)


def columns(profile):
    """Source-entry constraints and a free legal competitor; NEVER constrain output."""
    names = COLUMN_NAMES[profile]
    result = []
    for bits in product((0, 1), repeat=len(names)):
        env = dict(zip(names, bits))
        m, a, g, z = (env[k] for k in ('must', 'may', 'seed', 'alternative'))
        if profile == 'ascending':
            legal = m <= g <= a and m <= z <= a
        else:
            optional = a & (1 - m)
            legal = not g & optional and g <= z <= g + optional
        if legal:
            result.append(''.join(map(str, bits)))
    return tuple(result)


def initial(program):
    return tuple(0 if a['kind'] == 'order' else True for a in program['atoms'])


def valid_state(program, state):
    return (len(state) == len(program['atoms']) and all(
        integer(v, -1, 1) if a['kind'] == 'order' else type(v) is bool
        for a, v in zip(program['atoms'], state)))


def bit_value(expr, env):
    if type(expr) is str:
        return 0 if expr == 'zero' else 1 if expr == 'ones' else env[expr]
    op = expr[0]
    left = bit_value(expr[1], env)
    if op == 'bit_not':
        return 1 - left
    right = bit_value(expr[2], env)
    if op == 'bit_and': return left & right
    if op == 'bit_or': return left | right
    return left ^ right


def advance(program, state, env):
    result = []
    for atom, old in zip(program['atoms'], state):
        left, right = (bit_value(atom[k], env) for k in ('left', 'right'))
        kind = atom['kind']
        if kind == 'order': value = old if left == right else left - right
        elif kind == 'eq': value = old and left == right
        elif kind == 'subset': value = old and left <= right
        else: value = old and not (left & right)
        result.append(value)
    return tuple(result)


def observed(expr, state):
    if type(expr) is bool: return expr
    op = expr[0]
    if op == 'query': return state[expr[1]]
    if op == 'ult': return state[expr[1]] < 0
    if op == 'ule': return state[expr[1]] <= 0
    if op == 'not': return not observed(expr[1], state)
    if op == 'and': return all(observed(e, state) for e in expr[1:])
    if op == 'or': return any(observed(e, state) for e in expr[1:])
    return not observed(expr[1], state) or observed(expr[2], state)


def violation(program, state):
    if not all(observed(e, state) for e in program['preconditions']):
        return None
    for i, expr in enumerate(program['obligations']):
        if not observed(expr, state):
            return 'obligation_' + str(i)
    return None


def word_value(expr, values, mask):
    """Whole-integer interpretation, independent of the bit monitor/compiled DAG."""
    if type(expr) is str:
        return 0 if expr == 'zero' else mask if expr == 'ones' else values[expr]
    op = expr[0]
    left = word_value(expr[1], values, mask)
    if op == 'bit_not': return mask ^ left
    right = word_value(expr[2], values, mask)
    if op == 'bit_and': return left & right
    if op == 'bit_or': return left | right
    return left ^ right


def concrete_formula(expr, values):
    if type(expr) is bool: return expr
    op = expr[0]
    if op == 'not': return not concrete_formula(expr[1], values)
    if op == 'and': return all(concrete_formula(e, values) for e in expr[1:])
    if op == 'or': return any(concrete_formula(e, values) for e in expr[1:])
    if op == 'implies':
        return not concrete_formula(expr[1], values) or concrete_formula(expr[2], values)
    mask = (1 << values['width']) - 1
    left, right = (word_value(e, values, mask) for e in expr[1:])
    if op == 'eq': return left == right
    if op == 'ne': return left != right
    if op == 'ult': return left < right
    if op == 'ule': return left <= right
    if op == 'ugt': return left > right
    if op == 'uge': return left >= right
    if op == 'subset': return left & right == left
    return left & right == 0


def concrete_violation(spec, values):
    compile_spec(spec)
    profile = spec['profile']
    names = set(COLUMN_NAMES[profile]) | {'output'}
    require(type(values) is dict and set(values) == names | {'width'}, 'concrete word fields')
    require(integer(values['width'], 1, 4096), 'positive bounded witness width')
    mask = (1 << values['width']) - 1
    require(all(integer(values[k], 0, mask) for k in names), 'concrete word ranges')
    m, a, g, z = (values[k] for k in ('must', 'may', 'seed', 'alternative'))
    if profile == 'ascending':
        require(g & m == m and not g & ~a and z & m == m and not z & ~a,
                'legal masked entry and independent alternative')
    else:
        optional = a & ~m
        require(not g & optional and z & g == g and not z & ~(g | optional),
                'disjoint entry and independent optional alternative')
    if not all(concrete_formula(e, values) for e in spec['preconditions']):
        return None
    for i, expr in enumerate(spec['obligations']):
        if not concrete_formula(expr, values):
            return 'obligation_' + str(i)
    return None
