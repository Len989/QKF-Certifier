"""Homogeneous int/long arithmetic and a pure, terminal Boolean expression.

Equality atoms observe full words; logical connectives never select word values.
No promotion, cast, call, field, branch, shift or implicit method name semantics.
"""
import hashlib
import re

from research.observations.model import integer, require
from .frontend import BINARY, DAG, IDENT, KEYWORDS, UNARY, need, select

CONTRACT = 'modular-lsb-word-predicates-v1'
GOAL_SCHEMA = 'qkf-word-predicate-goal-v1'
MAX_ATOMS = 8
PREC = {'||': 1, '&&': 2, '|': 3, '^': 4, '&': 5,
        '==': 6, '!=': 6, '+': 7, '-': 7}


def formula_size(term, depth=0):
    need(depth < 32, 'Boolean expression depth budget')
    if term[0] in {'atom', 'literal'}:
        return 1
    size = 1 + sum(formula_size(x, depth + 1) for x in term[1:])
    need(size <= 128, 'expanded Boolean expression budget')
    return size


def read_source(source, entry, word_type):
    require(type(word_type) is str and word_type in {'int', 'long'}, 'homogeneous word type')
    ts, parameter, final_parameter, declaration, span = select(
        source, entry, word_type=word_type, result_type='boolean')
    need(len(ts) <= 2048, 'selected body token budget')
    dag, atoms, i = DAG(), [], 0
    env = {parameter: ('word', dag.node('input'))}
    finals = {parameter} if final_parameter else set()

    def take(expected=None):
        nonlocal i
        need(i < len(ts) and (expected is None or ts[i] == expected),
             'unsupported predicate token at ' + str(i))
        t = ts[i]
        i += 1
        return t

    def boolean(op, *args):
        term = [op, *args]
        formula_size(term)
        return ('bool', term)

    def expression(minimum=1, depth=0):
        need(depth < 32, 'predicate nesting budget')
        t = take()
        if t in {*UNARY, '!'}:
            typ, arg = expression(8, depth + 1)
            need(typ == ('bool' if t == '!' else 'word'), 'unary operand type')
            left = boolean('not', arg) if t == '!' else ('word', dag.node(UNARY[t], arg))
        elif t == '(':
            left = expression(1, depth + 1)
            take(')')
        elif t in env:
            left = env[t]
        elif t in {'true', 'false'}:
            left = boolean('literal', t == 'true')
        else:
            pattern = r'(0|[1-9][0-9]*)' + (r'[lL]' if word_type == 'long' else '')
            need(re.fullmatch(pattern, t) is not None, 'unsupported homogeneous primary: ' + t)
            n = int(t[:-1] if word_type == 'long' else t)
            need(n < 2 ** (63 if word_type == 'long' else 31), 'decimal literal range')
            left = ('word', dag.node('const', n))
        while i < len(ts) and PREC.get(ts[i], 0) >= minimum:
            op = take()
            right = expression(PREC[op] + 1, depth + 1)
            if op in BINARY:
                need(left[0] == right[0] == 'word', 'bitwise/arithmetic word operands')
                left = ('word', dag.node(BINARY[op], left[1], right[1]))
            elif op in {'==', '!='}:
                need(left[0] == right[0] == 'word', 'equality of homogeneous words only')
                pair = [left[1], right[1]]
                if pair not in atoms:
                    need(len(atoms) < MAX_ATOMS, 'equality atom budget')
                    atoms.append(pair)
                left = boolean('atom', atoms.index(pair))
                if op == '!=':
                    left = boolean('not', left[1])
            else:
                need(left[0] == right[0] == 'bool', 'logical Boolean operands')
                left = boolean('and' if op == '&&' else 'or', left[1], right[1])
        return left

    root = None
    while i < len(ts):
        t = take()
        if t == 'return':
            typ, root = expression()
            need(typ == 'bool', 'Boolean final result required')
            take(';')
            need(i == len(ts), 'no ignored trailing statements')
            break
        final = t == 'final'
        if final:
            t = take()
            need(t in {word_type, 'boolean'}, 'typed final local')
        declared = t in {word_type, 'boolean'}
        local_type = 'word' if t == word_type else 'bool'
        name = take() if declared else t
        need(IDENT.fullmatch(name) and name not in KEYWORDS and
             (name not in env if declared else name in env), 'known distinct local')
        need(name not in finals, 'assignment to final variable')
        take('=')
        value = expression()
        take(';')
        expected = local_type if declared else env[name][0]
        need(value[0] == expected, 'assignment type; no conversions')
        env[name] = value
        if final:
            finals.add(name)
    need(root is not None, 'actual Boolean return required')
    return {'contract': CONTRACT, 'word_type': word_type, 'entry': dict(entry),
            'nodes': dag.nodes, 'atoms': atoms, 'formula': root,
            'source_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(),
            'declaration_sha256': hashlib.sha256(declaration.encode('utf-8')).hexdigest(), 'span': span}


def goal(spec):
    require(type(spec) is dict and set(spec) == {'schema', 'contract', 'entry', 'word_type', 'target'},
            'predicate goal fields')
    require(spec['schema'] == GOAL_SCHEMA and spec['contract'] == CONTRACT, 'predicate goal contract')
    require(type(spec['word_type']) is str and spec['word_type'] in {'int', 'long'}, 'goal word type')
    entry = spec['entry']
    require(type(entry) is dict and set(entry) == {'class', 'method'} and
            all(type(v) is str and IDENT.fullmatch(v) for v in entry.values()), 'goal entry')
    nodes = 0

    def visit(t, depth=0):
        nonlocal nodes
        nodes += 1
        require(depth < 16 and nodes <= 64 and type(t) is list and t and type(t[0]) is str,
                'count goal tree budget')
        if t[0] in {'popcount_le', 'popcount_eq'}:
            require(len(t) == 2 and integer(t[1], 0, 3), 'count goal threshold 0..3')
            return t[1]
        require(t[0] in {'not', 'and', 'or'} and len(t) == (2 if t[0] == 'not' else 3),
                'independent count goal operator')
        return max(visit(x, depth + 1) for x in t[1:])

    return visit(spec['target']) + 1  # Saturate strictly above every observed threshold.


def target_value(t, count):
    op = t[0]
    if op == 'popcount_le': return count <= t[1]
    if op == 'popcount_eq': return count == t[1]
    if op == 'not': return not target_value(t[1], count)
    if op == 'and': return target_value(t[1], count) and target_value(t[2], count)
    if op == 'or': return target_value(t[1], count) or target_value(t[2], count)
    raise ValueError('unknown count goal operator')
