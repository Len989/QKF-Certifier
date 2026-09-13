"""Revision 2: a checked additive native bridge before boundary inference.

The first frozen run is preserved. This revision addresses its 12 neutral
add/sub representation failures with a general modular additive normal form.
"""
import collections
from qkf_certifier.kernel import digest,at,replace,Z,T
from regular_interfaces import tree
from symbolic_bridge import path_guards
from semantic_view import constant,LEAVES
import boundary_kernel as K

SCHEMA='qkf-boundary-action-v2-additive'
ACTIONS=K.ACTIONS
counts=K.counts


def normalize(e):
    steps=[]
    def walk(t):
        if t[0] in LEAVES:return t
        t=K.native((t[0],*(walk(c) for c in t[1:])))
        if t[0] not in {'add','sub'}:return t
        terms=collections.Counter();integer=0
        def collect(x,sign):
            nonlocal integer
            if x[0]=='add':collect(x[1],sign);collect(x[2],sign)
            elif x[0]=='sub':collect(x[1],sign);collect(x[2],-sign)
            elif x==Z:pass
            elif x==T:integer-=sign
            elif x[0]=='const':integer+=sign*x[1]
            else:terms[x]+=sign
        collect(t,1)
        if sum(abs(v) for v in terms.values())>128:raise ValueError('additive coefficient budget')
        positive=[];negative=[]
        for atom,v in sorted(terms.items(),key=lambda p:repr(p[0])):
            (positive if v>0 else negative).extend([atom]*abs(v))
        if integer>0:positive.append(constant(integer))
        elif integer<0:negative.append(constant(-integer))
        def total(xs):
            if not xs:return Z
            out=xs[0]
            for x in xs[1:]:out=('add',out,x)
            return out
        out=total(positive) if not negative else ('sub',total(positive),total(negative))
        out=K.native(out)
        steps.append(dict(before_hash=digest(t),coefficients=[dict(term=a,coefficient=v) for a,v in sorted(terms.items(),key=lambda p:repr(p[0])) if v],
            integer=integer,after_hash=digest(out)))
        return out
    out=walk(K.native(tree(e)))
    return out,steps


def native(e):return normalize(e)[0]


def derive(e,guards,engine):
    original=tree(e)
    if original[0] not in ACTIONS:raise ValueError('not a boundary consumer')
    amount,steps=normalize(original[2])
    normalized=(original[0],K.native(original[1]),amount)
    after,proof=K.derive(normalized,guards,engine)
    return after,dict(kind=proof['kind'],minimum_width=2,source_hash=digest(original),guards_hash=digest(guards),
        additive_bridge=dict(source=original[2],after=amount,steps=steps,law='additive group of integers modulo 2^w'),
        normalized_action=normalized,boundary_proof=proof,after_hash=digest(after))


def proof_steps(proof):
    if 'additive_bridge' not in proof:return K.proof_steps(proof)
    return len(proof['additive_bridge']['steps'])+K.proof_steps(proof['boundary_proof'])


def replay(initial,trace,expected):
    root=tree(initial);steps=0
    if len(trace)>1000:raise ValueError('boundary rewrite budget')
    for t in trace:
        if t['schema']!=SCHEMA:
            nxt=replace(root,t['path'],tree(t['after']));root,n=K.replay(root,[t],nxt);steps+=n;continue
        if t['minimum_width']!=2 or t['before_hash']!=digest(root):raise ValueError('boundary v2 source binding')
        g=path_guards(root,t['path']);after,proof=derive(at(root,t['path']),g,t['engine'])
        if digest(g)!=digest(t['guards']) or digest(proof)!=digest(t['proof']) or after!=tree(t['after']):raise ValueError('boundary v2 derivation mismatch')
        root=replace(root,t['path'],after);steps+=proof_steps(proof)
        if digest(root)!=t['after_hash']:raise ValueError('boundary v2 result binding')
    if root!=tree(expected):raise ValueError('boundary v2 final expression')
    return root,steps
