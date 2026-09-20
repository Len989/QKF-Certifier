"""Native evidence replay. Rules justify individual facts, never a target verdict."""
from research.ground_query.schema import fields, require
from research.signed_predicates.frontend import target_value
from .context import integer
from .encoding import SIGNED


def constant(ctx, i):
    row = ctx.ir['nodes'][i]
    return row[1] if row[0] == 'const' else None


def atom_constant(ctx, i):
    atom = ctx.ir['atoms'][i]
    if atom['kind'] == 'eq':
        for expr, value in ((atom['left'], atom['right']), (atom['right'], atom['left'])):
            k = constant(ctx, value)
            if k is not None:
                return expr, k
    return None


def mask_implication(ctx, g, a, b):
    integer(a, 0, len(ctx.ir['atoms']) - 1, 'antecedent atom')
    integer(b, 0, len(ctx.ir['atoms']) - 1, 'consequent atom')
    antecedent, consequent = atom_constant(ctx, a), atom_constant(ctx, b)
    if antecedent is None or consequent is None:
        return None
    x, k = antecedent
    masked, expected = consequent
    row = ctx.ir['nodes'][masked]
    if row[0] != 'and':
        return None
    for word, mask in (row[1:], row[1:][::-1]):
        m = constant(ctx, mask)
        if word == x and m is not None:
            actual = k & m
            if ctx.width is not None:
                actual %= 1 << ctx.width
                expected %= 1 << ctx.width
            if actual == expected:
                implication = g.node('b.or', g.node('b.not', g.atom(a)), g.atom(b))
                return implication, g.literal(True)
    return None


def dependencies(ctx, root):
    needed, todo = set(), [root]
    while todo:
        i = todo.pop()
        if i not in needed:
            needed.add(i)
            row = ctx.ir['nodes'][i]
            if row[0] not in ('input', 'const'):
                todo.extend(row[1:])
    return sorted(needed)


def bit_pair(row, known):
    op = row[0]
    if op == 'input':
        return (0, 1)
    if op == 'const':
        return (row[1] & 1,) * 2
    out = []
    for b in (0, 1):
        a = known[row[1]][b]
        c = known[row[2]][b] if len(row) == 3 else 0
        value = {'pos': lambda: a, 'neg': lambda: -a, 'not': lambda: ~a,
                 'add': lambda: a+c, 'sub': lambda: a-c, 'xor': lambda: a ^ c,
                 'and': lambda: a & c, 'or': lambda: a | c}[op]()
        out.append(value & 1)
    return tuple(out)


def masked_root(ctx, i):
    integer(i, 0, len(ctx.ir['nodes']) - 1, 'masked word index')
    row = ctx.ir['nodes'][i]
    if row[0] == 'and':
        for expr, mask in (row[1:], row[1:][::-1]):
            if constant(ctx, mask) == 1:
                return expr
    return None


def parity_evidence(ctx, i):
    root = masked_root(ctx, i)
    if root is None:
        return None
    values, rows = {}, []
    for j in dependencies(ctx, root):
        values[j] = bit_pair(ctx.ir['nodes'][j], values)
        rows.append({'node': j, 'bits': list(values[j])})
    return rows if values[root][0] == values[root][1] else None


def input_bridge(ctx, g, i):
    integer(i, 0, len(ctx.ir['atoms']) - 1, 'bridge atom')
    atom = ctx.ir['atoms'][i]
    if atom['kind'] == 'signed_zero' and ctx.ir['nodes'][atom['node']] == ['input']:
        return g.atom(i), g.node('t.' + SIGNED[atom['op']])
    pair = atom_constant(ctx, i)
    if pair is not None and ctx.ir['nodes'][pair[0]] == ['input'] and pair[1] == 0:
        return g.atom(i), g.node('t.popcount_eq.0')
    return None


def target_formula(g, i, cache=None):
    cache = {} if cache is None else cache
    if i not in cache:
        op, args = g.row(i)
        if op.startswith('t.'):
            parts = op.split('.')
            result = [parts[1]] + ([int(parts[2])] if len(parts) == 3 else [])
        elif op in ('b.true', 'b.false'):
            result = op == 'b.true'
        elif op in ('b.not', 'b.and', 'b.or', 'b.xor'):
            children = [target_formula(g, a, cache) for a in args]
            result = [op[2:], *children] if all(c is not None for c in children) else None
        else:
            result = None
        cache[i] = result
    return cache[i]


def target_eval(term, count, sign):
    if type(term) is bool:
        return term
    op = term[0]
    if op in ('not', 'and', 'or', 'xor'):
        values = [target_eval(c, count, sign) for c in term[1:]]
        if op == 'not': return not values[0]
        if op == 'and': return values[0] and values[1]
        if op == 'or': return values[0] or values[1]
        return values[0] != values[1]
    return target_value(term, count, sign)


def guard_truth(ctx, g, i):
    term = target_formula(g, i)
    if term is None or not ctx.domain:
        return None
    def covered(t):
        if type(t) is bool:
            return True
        if t[0] in ('popcount_eq', 'popcount_le'):
            return t[1] < ctx.limit
        return all(covered(c) for c in t[1:] if type(c) is list or type(c) is bool)
    if not covered(term):
        return None
    values = {target_eval(term, *s) for s in ctx.domain}
    if len(values) == 1:
        return i, g.literal(next(iter(values)))
    return None


def local_rhs(ctx, g, i):
    """One deterministic structural rewrite. No equations or source goals assumed."""
    op, args = g.row(i)
    if op == 't.nonnegative':
        return 'target-nonnegative', g.node('b.not', g.node('t.negative'))
    if op == 't.positive':
        return 'target-positive', g.node('b.and', g.node('b.not', g.node('t.negative')),
                                        g.node('b.not', g.node('t.popcount_eq.0')))
    if op == 't.nonpositive':
        return 'target-nonpositive', g.node('b.or', g.node('t.negative'), g.node('t.popcount_eq.0'))
    if op == 't.popcount_le.0':
        return 'target-zero', g.node('t.popcount_eq.0')
    if op.startswith('w.c') and ctx.width is not None:
        value = int(op[3:]) % (1 << ctx.width)
        if str(value) != op[3:]:
            return 'fixed-constant', g.node('w.c' + str(value))
    if op == 'w.eq':
        a, b = args
        if a == b:
            return 'eq-reflexive', g.literal(True)
        x, y = g.row(a)[0], g.row(b)[0]
        if x.startswith('w.c') and y.startswith('w.c'):
            left, right = int(x[3:]), int(y[3:])
            if ctx.width is not None:
                return 'eq-fixed-constants', g.literal(left % (1 << ctx.width) == right % (1 << ctx.width))
            if (left ^ right) & 1:
                return 'eq-distinct-low-bit', g.literal(False)
    if op in ('w.pos', 'w.neg', 'w.not'):
        a = args[0]
        if op == 'w.pos': return 'word-positive', a
        aop, aa = g.row(a)
        if aop == op: return 'word-involution', aa[0]
    if op in ('w.add', 'w.sub', 'w.and', 'w.or', 'w.xor'):
        a, b = args
        if a == b:
            if op in ('w.sub', 'w.xor'): return 'word-cancel', g.node('w.c0')
            if op in ('w.and', 'w.or'): return 'word-idempotent', a
        az, bz = g.row(a)[0] == 'w.c0', g.row(b)[0] == 'w.c0'
        if op == 'w.and' and (az or bz): return 'word-and-zero', g.node('w.c0')
        if op in ('w.add', 'w.or', 'w.xor') and (az or bz): return 'word-zero-neutral', b if az else a
        if op == 'w.sub' and bz: return 'word-sub-zero', a
    if op == 'b.not':
        aop, aa = g.row(args[0])
        if aop in ('b.true', 'b.false'): return 'not-literal', g.literal(aop == 'b.false')
        if aop == 'b.not': return 'double-not', aa[0]
    if op in ('b.and', 'b.or', 'b.xor'):
        a, b = args
        if a == b: return 'bool-idempotent', g.literal(False) if op == 'b.xor' else a
        for literal, other in ((a, b), (b, a)):
            lop, la = g.row(literal)
            if lop in ('b.true', 'b.false'):
                value = lop == 'b.true'
                if op == 'b.and': return 'and-literal', other if value else literal
                if op == 'b.or': return 'or-literal', literal if value else other
                return 'xor-literal', g.node('b.not', other) if value else other
            if lop == 'b.not' and la[0] == other:
                return 'bool-complement', g.literal(op != 'b.and')
        if op != 'b.xor':
            dual = 'b.or' if op == 'b.and' else 'b.and'
            for outer, inner in ((a, b), (b, a)):
                iop, ia = g.row(inner)
                if iop == dual and outer in ia: return 'bool-absorption', outer
    return None


def check_fact(ctx, g, fact):
    require(type(fact) is dict and type(fact.get('rule')) is str, 'native fact rule')
    rule = fact['rule']
    result = None
    if rule == 'eq-mask':
        fields(fact, ('rule', 'antecedent', 'consequent'), 'mask fact')
        result = mask_implication(ctx, g, fact['antecedent'], fact['consequent'])
    elif rule == 'low-bit':
        fields(fact, ('rule', 'masked_node', 'rows'), 'least-bit proof')
        root = masked_root(ctx, fact['masked_node'])
        require(root is not None, 'least-bit masking by one')
        needed, rows, known = dependencies(ctx, root), fact['rows'], {}
        require(type(rows) is list and len(rows) == len(needed), 'complete bit derivation')
        for node, row in zip(needed, rows):
            fields(row, ('node', 'bits'), 'bit derivation row')
            require(type(row['node']) is int and row['node'] == node, 'chronological bit node')
            bits = row['bits']
            require(type(bits) is list and len(bits) == 2 and all(type(b) is int and b in (0, 1) for b in bits),
                    'two typed bit cases')
            expected = bit_pair(ctx.ir['nodes'][node], known)
            require(tuple(bits) == expected, 'native least-bit rule mismatch')
            known[node] = expected
        require(known[root][0] == known[root][1], 'least bit is not constant')
        result = g.word(fact['masked_node']), g.node('w.c' + str(known[root][0]))
    elif rule == 'input-bridge':
        fields(fact, ('rule', 'atom'), 'input bridge')
        result = input_bridge(ctx, g, fact['atom'])
    elif rule == 'guard-zero':
        fields(fact, ('rule',), 'guard zero')
        require(ctx.domain and all(c == 0 for c, _ in ctx.domain), 'G does not force zero input')
        result = g.node('w.input'), g.node('w.c0')
    elif rule == 'guard-truth':
        fields(fact, ('rule', 'term'), 'guard truth')
        result = guard_truth(ctx, g, fact['term'])
    elif rule == 'local':
        fields(fact, ('rule', 'term', 'law'), 'local identity')
        rhs = local_rhs(ctx, g, fact['term'])
        require(rhs is not None and fact['law'] == rhs[0], 'inapplicable local identity')
        result = fact['term'], rhs[1]
    else:
        raise ValueError('unknown native rule')
    require(result is not None, 'native premise not established')
    return result
