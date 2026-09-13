"""Research conditional rewrite kernel, under positive width or width >= 2.

Rules are mathematical lemmas, documented in RULES_AND_PROOFS.md. This Python
implementation is not a Lean proof. Every step is checked against its actual
source path and surrounding true branch; producer annotations are not premises.
"""
from qkf_certifier.kernel import (children, at, replace, digest, disjoint, RULES,
                                 apply_rule, Z, T, W, C1, TRUE, FALSE)

RULE_NAMES = (
    'branch-value', 'bool-neutral', 'bool-idempotent', 'ones-bound-equality',
    'ones-implies-nonzero', 'literal-arithmetic', 'width-one-false',
    'width-at-least-one', 'shift-width', 'set-width', 'clear-width-plus-one',
    'clear-one-constant', 'sign-mask', 'set-low-width-minus-one',
    'divide-by-zero', 'remainder-special', 'trailing-one-set',
    'leading-one-nonzero', 'clear-leading-disjoint-underflow',
    'masked-leading-shift', 'masked-set-two', 'signed-zero-min',
    'signed-minus-one-max', 'distribute-select',
)


def clauses(e):
    return clauses(e[1]) + clauses(e[2]) if e[0] == 'booland' else [e]


def context(root, path):
    assumptions = []; node = root
    for i in path:
        if node[0] == 'select' and i == 2: assumptions.extend(clauses(node[1]))
        node = node[i]
    return assumptions


def substitutions(assumptions):
    out = {}
    for e in assumptions:
        if e[0] == 'cmp0':
            for a, b in ((e[1], e[2]), (e[2], e[1])):
                if a[0] == 'var' and a[1] < 4 and b in (Z, T): out[a] = b
        if e[0] == 'cmp7' and e[1] == T and e[2][0] == 'var' and e[2][1] < 4:
            out[e[2]] = T
    for a, b in list(out.items()):
        if b == T: out[('var', a[1] ^ 1)] = Z  # Known-zero/known-one disjointness.
    return out


def negative(x): return ('cmp2', x, Z)


def new_rule(rule, e, assumptions, min_width):
    op = e[0]; a = e[1] if len(e)>1 else None; b = e[2] if len(e)>2 else None
    if rule == 'branch-value' and e in substitutions(assumptions): return substitutions(assumptions)[e]
    if rule == 'bool-neutral':
        if op == 'booland' and a == TRUE: return b
        if op == 'booland' and b == TRUE: return a
        if op in ('boolor','boolxor') and a == FALSE: return b
        if op in ('boolor','boolxor') and b == FALSE: return a
    if rule == 'bool-idempotent' and a == b:
        if op in ('booland','boolor'): return a
        if op == 'boolxor': return FALSE
    if rule == 'ones-bound-equality':
        if op == 'cmp7' and a == T: return ('cmp0', b, T)
        if op == 'cmp9' and b == T: return ('cmp0', a, T)
    if rule == 'ones-implies-nonzero' and op == 'booland':
        for x, y in ((a,b),(b,a)):
            if x[0] == 'cmp0' and x[2] == T and y == ('cmp6', Z, x[1]): return x
    if rule == 'literal-arithmetic' and op in ('add','sub','and','or','xor'):
        def literal(x):
            if x == Z: return 0
            if x == T: return -1
            if x[0] == 'const': return x[1]
            return None
        x, y = literal(a), literal(b)
        if x is not None and y is not None:
            z = {'add':lambda:x+y,'sub':lambda:x-y,'and':lambda:x&y,'or':lambda:x|y,'xor':lambda:x^y}[op]()
            return Z if z == 0 else T if z == -1 else ('const',z)
    if rule == 'width-one-false' and min_width >= 2 and op == 'cmp0' and {a,b} == {W,C1}: return FALSE
    if rule == 'width-at-least-one' and op == 'umax' and {a,b} == {W,C1}: return W
    if rule == 'shift-width' and b == W:
        if op in ('shl','lshr'): return Z
        if op == 'ashr': return ('select', negative(a), T, Z)
    if rule == 'set-width' and op in ('set_high_bits','set_low_bits') and b == W: return T
    if rule == 'clear-width-plus-one' and min_width >= 2 and op in ('clear_high_bits','clear_low_bits') and b in (('add',W,C1),('add',C1,W)): return Z
    if rule == 'clear-one-constant' and op == 'clear_low_bits' and a == C1 and b == C1: return Z
    if rule == 'sign-mask' and b == C1:
        if op == 'clear_high_bits': return ('clear_sign_bit',a)
        if op == 'set_high_bits': return ('set_sign_bit',a)
    if rule == 'set-low-width-minus-one' and op == 'set_low_bits' and b == ('sub',W,C1): return ('or',a,('clear_sign_bit',T))
    if rule == 'divide-by-zero' and op == 'udiv' and b == Z: return T
    if rule == 'remainder-special':
        if op in ('urem','srem') and b == Z: return a
        if op == 'srem' and b in (T,C1): return Z
    if rule == 'trailing-one-set' and op == 'set_low_bits' and b == ('countr_one',a): return a
    if rule == 'leading-one-nonzero' and op == 'cmp7' and a == C1 and b[0] == 'countl_one': return negative(b[1])
    if rule == 'clear-leading-disjoint-underflow' and op == 'clear_high_bits' and b[0] == 'umax':
        for p, c in ((b[1],b[2]),(b[2],b[1])):
            if c[0] == 'countl_one' and p == ('sub',c,C1) and disjoint(a,c[1]): return ('select',negative(c[1]),a,Z)
    if rule == 'masked-leading-shift' and op == 'and':
        for x, y in ((a,b),(b,a)):
            if y[0] == 'lshr' and y[1] == T and y[2][0] == 'countl_one' and disjoint(x,y[2][1]): return x
    if rule == 'masked-set-two' and op == 'and' and min_width >= 2:
        for x, s in ((a,b),(b,a)):
            if s[0] != 'smax': continue
            for c, z in ((s[1],s[2]),(s[2],s[1])):
                if z != Z or c[0] != 'clear_high_bits' or c[1][0] != 'set_high_bits': continue
                y, n = c[1][1:]
                if n == ('const',2) and c[2] == ('countl_one',y) and disjoint(x,y):
                    return ('select',negative(y),('and',x,('lshr',('set_sign_bit',Z),C1)),Z)
    if rule == 'signed-zero-min' and op == 'smin' and (a == Z or b == Z):
        x = b if a == Z else a
        return ('select',negative(x),x,Z)
    if rule == 'signed-minus-one-max' and op == 'smax' and (a == T or b == T):
        x = b if a == T else a
        return ('select',negative(x),T,x)
    if rule == 'distribute-select':
        # Pure total expressions: distribute one argument over its two branches.
        allowed = {'not','srem','urem','clear_high_bits'}
        if op in allowed:
            for i in children(e):
                t = e[i]
                if t[0] == 'select':
                    lo=list(e);hi=list(e);lo[i]=t[2];hi[i]=t[3]
                    return ('select',t[1],tuple(lo),tuple(hi))
    raise ValueError('inapplicable research rule '+rule)


def step(root, path, rule, min_width):
    node = at(root,path)
    value = apply_rule(rule[4:],node) if rule.startswith('qkf:') else new_rule(rule,node,context(root,path),min_width)
    if value == node: raise ValueError('unchanged rewrite')
    return replace(root,path,value)


def produce(initial, min_width=2, max_steps=10000):
    root = initial; trace = []
    def attempt(path):
        nonlocal root
        for rule in (*RULE_NAMES, *('qkf:'+r for r in RULES)):
            try: result = step(root,path,rule,min_width)
            except ValueError: continue
            trace.append({'path':list(path),'rule':rule,'before':digest(at(root,path)),
                          'after':digest(at(result,path))})
            root=result
            if len(trace) > max_steps: raise RuntimeError('rewrite budget exceeded')
            return True
        return False
    def visit(path):
        while attempt(path): pass
        for i in children(at(root,path)): visit(path+[i])
        if attempt(path): visit(path)
    visit([])
    return root, trace


def replay(initial, trace, expected, min_width=2):
    root=initial
    for s in trace:
        if digest(at(root,s['path'])) != s['before']: raise ValueError('before mismatch')
        root=step(root,s['path'],s['rule'],min_width)
        if digest(at(root,s['path'])) != s['after']: raise ValueError('after mismatch')
    if root != expected: raise ValueError('final mismatch')
    return root
