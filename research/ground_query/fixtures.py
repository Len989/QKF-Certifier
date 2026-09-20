"""Development inputs from Paper II definitions, not external observations."""

from itertools import combinations_with_replacement
from .schema import INPUT_SCHEMA


def term(op, *args):
    return (op, *args)


def power(k, t):
    for _ in range(k):
        t = term('f', t)
    return t


def encode(signature, equations, queries, sorts=('A',)):
    nodes, ids = [], {}
    def node(t):
        if t not in ids:
            args = [node(a) for a in t[1:]]
            ids[t] = len(nodes)
            nodes.append({'op': t[0], 'args': args})
        return ids[t]
    eqs = [[node(a), node(b)] for a, b in equations]
    goals = [[node(a), node(b)] for a, b in queries]
    return {'schema': INPUT_SCHEMA, 'sorts': list(sorts), 'signature': signature,
            'nodes': nodes, 'equations': eqs, 'queries': goals}


def unary_signature(constants):
    return {**{t[0]: {'args': [], 'result': 'A'} for t in constants},
            'f': {'args': ['A'], 'result': 'A'}}


def gap():
    p, q, r = (term(x) for x in ('p', 'q', 'r'))
    equations = [(p, power(2, r)), (q, power(2, r))]
    return encode(unary_signature([p, q, r]), equations, [(power(1, p), power(1, q))])


def catalan_cases():
    for h in range(1, 6):
        profiles = (p for p in combinations_with_replacement(range(h + 1), h)
                    if all(i <= v for i, v in enumerate(p)))
        for ordinal, profile in enumerate(profiles):
            equations, constants = [], []
            for i, v in enumerate(profile):
                if v > i:
                    p, q, r = [term(f'{x}{i}') for x in 'pqr']
                    constants.extend((p, q, r))
                    equations.extend(((power(i, p), power(v, r)), (power(i, q), power(v, r))))
            if h not in profile:
                u, v = term('u'), term('v')
                constants.extend((u, v))
                equations.append((power(h, u), power(h, v)))
            pool = [power(d, c) for d in range(h + 1) for c in constants]
            # Every term, reflexive pair and unordered pair of complete T^h.
            queries = [(a, b) for i, a in enumerate(pool) for b in pool[i:]]
            yield f'catalan_h{h}_{ordinal:03d}', profile, encode(unary_signature(constants), equations, queries)


def shared_example():
    A = [term(str(i)) for i in range(4)]
    b = term('b')
    f = lambda x, y: term('f', x, y)
    alpha = lambda x, y: term('alpha', x, y)
    table = [[0, 2, 0, 0], [1, 2, 1, 3], [0, 2, 2, 0], [3, 0, 3, 0]]
    rows = [alpha(b, x) for x in A]
    native = [(f(A[i], A[j]), A[table[i][j]]) for i in range(4) for j in range(4)]
    observed = [(rows[i], A[v]) for i, v in ((0, 0), (2, 2), (3, 0))]
    compat = [(alpha(b, f(A[i], A[j])), f(rows[i], rows[j])) for i in range(4) for j in range(4)]
    sig = {str(i): {'args': [], 'result': 'A'} for i in range(4)}
    sig.update(b={'args': [], 'result': 'B'}, f={'args': ['A', 'A'], 'result': 'A'},
               alpha={'args': ['B', 'A'], 'result': 'A'})
    q = A + rows
    return encode(sig, native + observed + compat, [(x, y) for i, x in enumerate(q) for y in q[i:]], ('A', 'B'))


def examples():
    original = gap()
    yield 'gap', original
    flat = {**original, 'equations': original['equations'] + [[0, 3]]}
    # p and q are the left endpoints of the two displayed equations.
    flat['equations'][-1] = [original['equations'][0][0], original['equations'][1][0]]
    yield 'flattened', flat
    yield 'shared_typed', shared_example()
    yield 'empty', encode({'f': {'args': ['A'], 'result': 'B'}}, [], [], ('A', 'B'))
    a, b = term('a'), term('b')
    yield 'nonconsequence', encode(unary_signature([a, b]), [], [(a, b), (a, a)])
    sig = unary_signature([a, b])
    sig['unused'] = {'args': ['Empty'], 'result': 'A'}
    yield 'empty_sort', encode(sig, [], [(a, b)], ('A', 'Empty'))
