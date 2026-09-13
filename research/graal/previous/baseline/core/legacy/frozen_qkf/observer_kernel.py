"""Checked observational identities extending the frozen source-rewrite kernel.

All premises come from syntax, a checked minimum width, and existing KnownBits
path context. No operator-family name or producer-supplied assumption is a rule.
This Python semantic implementation is trusted, with proofs in OBSERVER_PROOFS.md.
"""
from functools import lru_cache
from qkf_certifier.kernel import (children, at, replace, digest, RULES, lowbit,
                                 Z, T, W, C1, TRUE, FALSE)
import guard_kernel

EXTENSION = 'qkf-observer-identities-v1'
RULE_NAMES = (
    'width-comparison', 'count-boundary-zero', 'literal-count', 'literal-not',
    'literal-order', 'unsigned-unit-bound', 'unsigned-smax-threshold',
    'unit-right-shift', 'count-zero-test', 'terminal-window',
    'distribute-observer-select', 'shifted-leading-mask',
)
COUNTS = {'countl_one', 'countl_zero', 'countr_one', 'countr_zero'}


def literal(t):
    if t == Z: return 0
    if t == T: return -1
    return t[1] if t[0] == 'const' else None


def constant(n):
    return Z if n == 0 else T if n == -1 else ('const', n)


@lru_cache(None)
def known_sign(t, minimum):
    value = literal(t)
    if value is not None and -(1 << (minimum - 1)) <= value < (1 << (minimum - 1)):
        return int(value < 0)
    op = t[0]
    if op == 'clear_sign_bit': return 0
    if op == 'set_sign_bit': return 1
    if op == 'not':
        bit = known_sign(t[1], minimum)
        return None if bit is None else bit ^ 1
    if op in ('and', 'or', 'xor'):
        a, b = known_sign(t[1], minimum), known_sign(t[2], minimum)
        if op == 'and' and (a == 0 or b == 0): return 0
        if op == 'or' and (a == 1 or b == 1): return 1
        if a is None or b is None: return None
        return a & b if op == 'and' else a | b if op == 'or' else a ^ b
    return None


def affine_width(t):
    """Coefficients a,b for a*w+b modulo 2**w; no inequalities inferred here."""
    if t == W: return 1, 0
    value = literal(t)
    if value is not None: return 0, value
    if t[0] in ('add', 'sub'):
        a, b = affine_width(t[1]), affine_width(t[2])
        if a is not None and b is not None:
            sign = 1 if t[0] == 'add' else -1
            return a[0] + sign * b[0], a[1] + sign * b[1]
    return None


def cmp_from_relation(op, signed_relation, unsigned_relation):
    s, u = signed_relation, unsigned_relation
    return (u == 0, u != 0, s < 0, s <= 0, s > 0, s >= 0,
            u < 0, u <= 0, u > 0, u >= 0)[int(op[3:])]


def high_window(k):
    result = Z; bit = ('set_sign_bit', Z)
    for _ in range(k):
        result = bit if result == Z else ('or', result, bit)
        bit = ('lshr', bit, C1)
    return result


def new_rule(rule, e, minimum):
    if minimum < 1: raise ValueError('positive width required')
    op = e[0]; a = e[1] if len(e) > 1 else None; b = e[2] if len(e) > 2 else None
    if rule == 'width-comparison' and op in {'cmp0', 'cmp1', 'cmp6', 'cmp7', 'cmp8', 'cmp9'}:
        rel = None
        if a == W and (b == Z or (b == C1 and minimum >= 2)): rel = 1
        if b == W and (a == Z or (a == C1 and minimum >= 2)): rel = -1
        if rel is not None: return TRUE if cmp_from_relation(op, rel, rel) else FALSE
    if rule == 'count-boundary-zero' and op in COUNTS:
        observed = known_sign(a, minimum) if op.startswith('countl') else lowbit(a)
        desired = int(op.endswith('one'))
        if observed is not None and observed != desired: return Z
    if rule == 'literal-count' and op in COUNTS:
        value = literal(a)
        if value is not None:
            if (op.endswith('zero') and value == 0) or (op.endswith('one') and value == -1): return W
            if op == 'countl_one' and value < 0:
                k = (~value).bit_length()
                if minimum >= k: return W if k == 0 else ('sub', W, constant(k))
            if op == 'countl_zero' and value > 0:
                k = value.bit_length()
                if minimum >= k: return ('sub', W, constant(k))
            if op.startswith('countr'):
                nonzero = value if op.endswith('zero') else ~value
                if nonzero:
                    k = (nonzero & -nonzero).bit_length() - 1
                    if minimum >= k: return constant(k)
    if rule == 'literal-not' and op == 'not' and literal(a) is not None:
        return constant(~literal(a))
    if rule == 'literal-order' and (op.startswith('cmp') or op in {'umin', 'umax', 'smin', 'smax'}):
        x, y = literal(a), literal(b); limit = 1 << (minimum - 1)
        if x is not None and y is not None and -limit <= x < limit and -limit <= y < limit:
            sr = (x > y) - (x < y)
            ux, uy = x % (2 * limit), y % (2 * limit); ur = (ux > uy) - (ux < uy)
            if op.startswith('cmp'): return TRUE if cmp_from_relation(op, sr, ur) else FALSE
            rel = sr if op.startswith('s') else ur
            choose_a = rel <= 0 if op.endswith('min') else rel >= 0
            return a if choose_a else b
    if rule == 'unsigned-unit-bound':
        if op == 'cmp6' and b == C1: return ('cmp0', a, Z)
        if op == 'cmp8' and a == C1: return ('cmp0', b, Z)
    if rule == 'unsigned-smax-threshold' and op == 'cmp6' and b[0] == 'smax':
        for x, c in ((b[1], b[2]), (b[2], b[1])):
            if a == x and known_sign(c, minimum) == 0: return ('cmp6', x, c)
    if rule == 'unit-right-shift' and a == C1:
        if op == 'lshr' or (op == 'ashr' and minimum >= 2):
            return ('select', ('cmp0', b, Z), C1, Z)
    if rule == 'count-zero-test' and op in ('cmp0', 'cmp1'):
        for c, z in ((a, b), (b, a)):
            if z != Z or c[0] not in COUNTS: continue
            equal = op == 'cmp0'
            if c[0].startswith('countl'):
                sign = int(c[0].endswith('zero')) if equal else int(c[0].endswith('one'))
                return ('cmp2' if sign else 'cmp5', c[1], Z)
            bit = ('and', c[1], C1)
            want_zero = (c[0].endswith('one') == equal)
            return ('cmp0' if want_zero else 'cmp1', bit, Z)
    if rule == 'terminal-window' and op == 'clear_low_bits':
        ab = affine_width(b)
        if ab is not None and ab[0] == 1:
            k = -ab[1]
            if 0 <= k <= minimum: return Z if k == 0 else ('and', a, high_window(k))
    if rule == 'distribute-observer-select' and op in {'clear_low_bits', 'umin', 'umax'}:
        for i in children(e):
            t = e[i]
            if t[0] == 'select':
                lo, hi = list(e), list(e); lo[i] = t[2]; hi[i] = t[3]
                return ('select', t[1], tuple(lo), tuple(hi))
    if rule == 'shifted-leading-mask' and op == 'lshr' and a[0] == 'set_high_bits' and a[1] == Z:
        count = a[2]
        if count[0] == 'countl_one' and count[1][0] == 'shl' and count[1][2] == b:
            x = count[1][1]; top = ('set_high_bits', Z, b)
            extended = ('set_high_bits', Z, ('countl_one', ('or', x, top)))
            return ('and', extended, ('not', top))
    raise ValueError('inapplicable observer rule ' + rule)


def step(root, path, rule, minimum):
    if rule.startswith('obs:'):
        old = at(root, path); value = new_rule(rule[4:], old, minimum)
        if value == old: raise ValueError('unchanged rewrite')
        return replace(root, path, value)
    if rule.startswith('guard:'): return guard_kernel.step(root, path, rule[6:], minimum)
    if rule.startswith('qkf:'): return guard_kernel.step(root, path, rule, minimum)
    raise ValueError('unknown observer trace rule')


def produce(initial, min_width=2, max_steps=10000):
    root = initial; trace = []
    rules = tuple('obs:' + r for r in RULE_NAMES) + tuple('guard:' + r for r in guard_kernel.RULE_NAMES) + tuple('qkf:' + r for r in RULES)
    def attempt(path):
        nonlocal root
        for rule in rules:
            try: result = step(root, path, rule, min_width)
            except ValueError: continue
            trace.append({'path': list(path), 'rule': rule, 'before': digest(at(root, path)), 'after': digest(at(result, path))})
            root = result
            if len(trace) > max_steps: raise RuntimeError('observer rewrite budget exceeded')
            return True
        return False
    def visit(path):
        while attempt(path): pass
        for i in children(at(root, path)): visit(path + [i])
        if attempt(path): visit(path)
    visit([])
    return root, trace


def replay(initial, trace, expected, min_width=2):
    root = initial
    for s in trace:
        if digest(at(root, s['path'])) != s['before']: raise ValueError('observer before mismatch')
        root = step(root, s['path'], s['rule'], min_width)
        if digest(at(root, s['path'])) != s['after']: raise ValueError('observer after mismatch')
    if root != expected: raise ValueError('observer final mismatch')
    return root
