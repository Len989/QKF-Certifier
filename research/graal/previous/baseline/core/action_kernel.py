"""Checked native semantic bridges and finite observations of modular actions.

This is a new trusted semantic layer, not a theorem prover imported from search.
Width-tail obligations use explicit base/induction checks for C*2**w+A*w+B.
No rule changes a target, a source guard, or the native total-word semantics.
"""
from qkf_certifier.kernel import at, replace, digest, Z, T, W
from regular_interfaces import tree

SCHEMA = 'qkf-native-action-observation-v1'
ONE = ('const', 1)
COUNTS = {'countl_zero', 'countl_one', 'countr_zero', 'countr_one'}
SHIFTS = {'shl', 'lshr', 'ashr'}
MASKS = {'clear_low_bits', 'clear_high_bits', 'set_low_bits', 'set_high_bits'}
MAX_THRESHOLD = 8


def signfill(x):
    return ('select', ('cmp2', x, Z), T, Z)


def elementary(e):
    """Elementary identities, with their complete total-semantics side cases."""
    op = e[0]
    if op in {'urem', 'srem'} and e[1] == e[2]:
        return Z, 'remainder-self-including-zero'
    if op in {'sdiv', 'udiv'} and e[1] == Z:
        return ('select', ('cmp0', e[2], Z), T, Z), 'zero-dividend-total'
    if op in {'sdiv', 'udiv'} and e[2] == ONE:
        return e[1], 'divide-one-including-width-one'
    if op == 'sdiv' and e[2] == T:
        return ('sub', Z, e[1]), 'signed-divide-minus-one-modular'
    if op == 'udiv' and e[2] == T:
        return ('select', ('cmp0', e[1], T), ONE, Z), 'unsigned-divide-maximum'
    if op == 'udiv' and e[1] == e[2]:
        return ('select', ('cmp0', e[1], Z), T, ONE), 'unsigned-divide-self-total'
    if op == 'urem' and e[2] == T:
        return ('select', ('cmp0', e[1], T), Z, e[1]), 'unsigned-remainder-maximum'
    if op == 'urem' and e[1] == ONE:
        return ('select', ('cmp0', e[2], ONE), Z, ONE), 'unsigned-remainder-one-dividend'
    if op == 'srem' and e[2] in {ONE, T}:
        return Z, 'signed-remainder-unit'
    if op == 'srem' and e[1] == ONE:
        unit = ('boolor', ('cmp0', e[2], ONE), ('cmp0', e[2], T))
        return ('select', unit, Z, ONE), 'signed-remainder-one-dividend'
    if op == 'mul' and T in e[1:]:
        return ('sub', Z, e[2] if e[1] == T else e[1]), 'multiply-minus-one-modular'
    raise ValueError('no elementary bridge')


def count_zero(n):
    x = n[1]
    if n[0] == 'countl_zero': return ('cmp2', x, Z)
    if n[0] == 'countl_one': return ('cmp5', x, Z)
    if n[0] == 'countr_zero': return ('cmp1', ('and', x, ONE), Z)
    if n[0] == 'countr_one': return ('cmp0', ('and', x, ONE), Z)
    raise ValueError('not a native run count')


def count_full(n):
    if n[0] not in COUNTS: raise ValueError('not a native run count')
    return ('cmp0', n[1], T if n[0].endswith('one') else Z)


def dependent_count_action(e):
    """Uniform-in-x two-class quotients for -n and n-w modulo 2**w."""
    if e[0] not in SHIFTS: raise ValueError('not a shift')
    x, amount = e[1:]
    n = None
    if amount[0] == 'sub':
        a, b = amount[1:]
        if a == Z and b[0] in COUNTS: n = b
        if a[0] == 'sub' and a[1] == b and a[2][0] in COUNTS: n = a[2]
    if n is not None:
        pred, family = count_zero(n), 'negative-bounded-count'
        count = n
    elif amount[0] == 'sub' and amount[2] == W and amount[1][0] in COUNTS:
        count = amount[1]; pred, family = count_full(count), 'count-minus-width'
    else:
        raise ValueError('no supported count action factor')
    saturated = signfill(x) if e[0] == 'ashr' else Z
    after = ('select', pred, x, saturated)
    proof = dict(family=family, count=count, exact_count_range=[0, 'w'],
                 modulus_lower_bound=dict(base_width=1, base_margin=0,
                     induction_difference='2^w-2 >= 0'),
                 classes=['identity', 'saturated'],
                 observation=pred, uniform_in_input_word=True)
    return after, proof


def plus(a, b): return tuple(x+y for x, y in zip(a, b))
def minus(a, b): return tuple(x-y for x, y in zip(a, b))
MOD = (1, 0, 0)
UNIT = (0, 0, 1)


def ge_zero(v, threshold):
    """Induction certificate for v(w)>=0 for every w>=threshold.

    v(w+1)-v(w)=C*2**w+A. C>=0 makes its minimum the base value.
    """
    c, a, b = v
    base = c*(1 << threshold)+a*threshold+b
    increment = c*(1 << threshold)+a
    if c < 0 or base < 0 or increment < 0:
        raise ValueError('unproved exponential-affine lower bound')
    return dict(expression=v, threshold=threshold, base=base,
                minimum_increment=increment, exponential_coefficient=c)


def canonical(v, threshold):
    # Integer multiples of 2**w disappear under word arithmetic. Select the
    # representative using checked bounds, never by a finite-width sample.
    _, a, b = v
    for c in (0, 1):
        r = (c, a, b)
        try:
            lo = ge_zero(r, threshold)
            hi = ge_zero(minus(minus(MOD, r), UNIT), threshold)
            return r, dict(lower=lo, upper_strict=hi)
        except ValueError:
            pass
    raise ValueError('no checked modular representative')


def width_tail(e, threshold):
    """A derivation for a width-only scalar expression on the infinite tail.

    Supported syntax is explicit; input variables and native counts are NOT
    mistaken for independent constants or for ordinary integer widths.
    """
    steps = []
    memo = {}
    def visit(t):
        if t in memo: return memo[t]
        op = t[0]; premises = []; evidence = None
        if t == W: value = (0, 1, 0)
        elif t == Z: value = (0, 0, 0)
        elif t == T: value = (1, 0, -1)
        elif op == 'const': value, evidence = canonical((0, 0, t[1]), threshold)
        elif op in {'true', 'false'}: value = op == 'true'
        elif op in {'add', 'sub', 'umin', 'umax'} or op in {'cmp'+str(i) for i in (0,1,6,7,8,9)}:
            a, b = visit(t[1]), visit(t[2]); premises = [digest(t[1]), digest(t[2])]
            if not isinstance(a, tuple) or not isinstance(b, tuple): raise ValueError('word type')
            if op in {'add', 'sub'}:
                value, evidence = canonical(plus(a,b) if op=='add' else minus(a,b), threshold)
            else:
                # Exact equality, or a strict ordering proved by induction.
                if a == b: relation, evidence = 0, dict(identical=True)
                else:
                    try: evidence=ge_zero(minus(minus(b,a),UNIT),threshold); relation=-1
                    except ValueError: evidence=ge_zero(minus(minus(a,b),UNIT),threshold); relation=1
                if op == 'umin': value = a if relation <= 0 else b
                elif op == 'umax': value = a if relation >= 0 else b
                else: value = {0:relation==0,1:relation!=0,6:relation<0,7:relation<=0,8:relation>0,9:relation>=0}[int(op[3:])]
        elif op == 'select':
            pred = visit(t[1])
            if type(pred) is not bool: raise ValueError('predicate type')
            chosen = t[2] if pred else t[3]
            value = visit(chosen); premises = [digest(t[1]),digest(chosen)]
            evidence = dict(selected=2 if pred else 3)
        else: raise ValueError('not supported width-only syntax: '+op)
        if isinstance(value, tuple):
            # In particular validate native width, zero and all-ones leaves.
            ge_zero(value,threshold);ge_zero(minus(minus(MOD,value),UNIT),threshold)
        steps.append(dict(node=digest(t),operation=op,premises=premises,value=value,evidence=evidence))
        memo[t] = value
        return value
    value = visit(e)
    if not isinstance(value, tuple): raise ValueError('amount must be a word')
    return value, steps


def eval_width(e, w):
    """Exact arithmetic for finitely many declared exceptional widths."""
    op = e[0]; m = (1 << w)-1
    if e == W: return w
    if e == Z: return 0
    if e == T: return m
    if op == 'const': return e[1] & m
    if op in {'true','false'}: return op=='true'
    if op == 'select': return eval_width(e[2] if eval_width(e[1],w) else e[3],w)
    if op not in {'add','sub','umin','umax','cmp0','cmp1','cmp6','cmp7','cmp8','cmp9'}: raise ValueError('width-only concrete grammar')
    a,b=eval_width(e[1],w),eval_width(e[2],w)
    if op=='add':return (a+b)&m
    if op=='sub':return (a-b)&m
    if op=='umin':return min(a,b)
    if op=='umax':return max(a,b)
    return {0:a==b,1:a!=b,6:a<b,7:a<=b,8:a>b,9:a>=b}[int(op[3:])]


def action_expression(op, x, label):
    kind = label[0]
    if kind == 'saturated':
        if op in {'shl','lshr'}: return Z
        if op == 'ashr': return signfill(x)
        return T if op.startswith('set_') else Z
    if kind == 'top-bit':
        if op != 'lshr': raise ValueError('top-bit action')
        return ('select',('cmp2',x,Z),ONE,Z)
    if kind != 'constant': raise ValueError('unknown action')
    k=label[1]
    if not 0<=k<=8: raise ValueError('finite action bound')
    if k==0:return x
    if op in SHIFTS:
        value=x
        for _ in range(k):value=(op,value,ONE)
        return value
    return (op,x,('const',k))


def width_is(k):
    # Exactly w=k among all positive widths, with ordinary word constants.
    return ('booland',('cmp0',('const',1<<k),Z),('cmp1',('const',1<<(k-1)),Z))


def width_action(e, threshold):
    if e[0] not in SHIFTS | MASKS: raise ValueError('not an action')
    if type(threshold) is not int or not 1<=threshold<=MAX_THRESHOLD: raise ValueError('threshold bound')
    op,x,amount=e
    if amount[0]=='const' or amount in (Z,T): raise ValueError('leave primitive amounts to old rules')
    v,steps=width_tail(amount,threshold)
    tail_evidence=None
    if v[0]==v[1]==0 and 0<=v[2]<=min(8,threshold-1): tail=('constant',v[2])
    elif op=='lshr' and v==(0,1,-1): tail=('top-bit',)
    else: tail_evidence=ge_zero(minus(v,(0,1,0)),threshold); tail=('saturated',)
    out=action_expression(op,x,tail); exceptions=[]
    for w in range(1,threshold):
        n=eval_width(amount,w)
        if type(n) is not int or not 0<=n<(1<<w):raise ValueError('exception word range')
        label=('saturated',) if n>=w else ('constant',n)
        branch=action_expression(op,x,label)
        # For the special top-bit label, directly compare equivalent small
        # word actions: at w it is shift by w-1.
        equivalent=label==tail or (tail==('top-bit',) and n==w-1)
        exceptions.append(dict(width=w,amount=n,action=label,equals_tail=equivalent))
        if not equivalent:out=('select',width_is(w),branch,out)
    proof=dict(family='width-action-quotient',threshold=threshold,tail_value=v,
               tail_derivation=steps,tail_action=tail,tail_bound=tail_evidence,
               exceptional_widths=exceptions)
    return out,proof


def apply_rule(e, rule, parameter=None):
    if rule=='elementary':
        after,name=elementary(e);return after,dict(family='elementary',identity=name)
    if rule=='dependent-count-action':return dependent_count_action(e)
    if rule=='width-action':return width_action(e,parameter)
    raise ValueError('unknown native action rule')


def replay(initial, trace, expected):
    if not isinstance(trace,list) or len(trace)>2000:raise ValueError('native trace bound')
    root=initial
    for record in trace:
        if record['schema']!=SCHEMA or record['before_hash']!=digest(root):raise ValueError('native root binding')
        path=record['path']
        if not isinstance(path,list) or any(type(i) is not int or i<1 for i in path):raise ValueError('native path')
        old=at(root,path)
        if record['source_hash']!=digest(old):raise ValueError('native source binding')
        after,proof=apply_rule(old,record['rule'],record.get('parameter'))
        if tree(record['after'])!=after or tree_value(record['proof'])!=tree_value(proof):raise ValueError('native derivation')
        root=replace(root,path,after)
        if record['after_hash']!=digest(root):raise ValueError('native result binding')
    if root!=tree(expected):raise ValueError('native final mismatch')
    return root


def tree_value(x):
    if isinstance(x,dict):return {k:tree_value(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return tuple(tree_value(v) for v in x)
    return x
