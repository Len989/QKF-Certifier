"""Deterministic native semantic view, not a search over equivalent programs.

All laws are total-word identities, valid independently of KnownBits masks.
Order selection, predicate polarity and associative/commutative presentation
are shared by all consumers. No new SMT or equality-saturation engine.
"""
from functools import lru_cache
from regular_interfaces import tree,order
from qkf_certifier.kernel import Z,T,W,digest

TRUE=('true',);FALSE=('false',);ONE=('const',1)
LEAVES={'var','zero','ones','width','const','true','false'}
AC={'add','and','or','xor','booland','boolor','boolxor'}


def literal(e):
    if e==Z:return 0
    if e==T:return -1
    if e[0]=='const':return e[1]
    return None


def constant(k):return Z if k==0 else T if k==-1 else ('const',k)
def negbool(p):return ('boolxor',p,TRUE)


def polarity(p):
    truth=True
    while p[0]=='boolxor' and TRUE in p[1:]:
        p=p[2] if p[1]==TRUE else p[1];truth=not truth
    return p,truth


def choose(kind,a,b):
    a,b=sorted([a,b],key=repr);p=('cmp2' if kind.startswith('s') else 'cmp6',a,b)
    return ('select',p,a,b) if kind.endswith('min') else ('select',p,b,a)


@lru_cache(maxsize=20000)
def view(e):
    if e[0] in LEAVES:
        return constant(e[1]) if e[0]=='const' else e
    op=e[0];xs=tuple(view(x) for x in e[1:])
    if op in {'umin','umax','smin','smax'}:
        if xs[0]==xs[1]:return xs[0]
        return choose(op,*xs)
    if op.startswith('cmp'):
        p=int(op[3:]);a,b=xs
        if p in {0,1}:
            a,b=sorted([a,b],key=repr);out=TRUE if a==b else ('cmp0',a,b)
            return view(negbool(out)) if p==1 else out
        base='cmp2' if p<6 else 'cmp6'
        q=p if p<6 else p-4
        if a==b:return TRUE if q in {3,5} else FALSE
        out=(base,b,a) if q in {3,4} else (base,a,b)
        return negbool(out) if q in {3,5} else out
    if op=='select':
        p,a,b=xs;p,positive=polarity(p)
        if not positive:a,b=b,a
        if p==TRUE:return a
        if p==FALSE:return b
        if a==b:return a
        if p[0] in {'cmp2','cmp6'}:
            kind='s' if p[0]=='cmp2' else 'u'
            if (a,b)==p[1:]:return choose(kind+'min',a,b)
            if (b,a)==p[1:]:return choose(kind+'max',a,b)
        return ('select',p,a,b)
    if op=='not':
        a=xs[0];k=literal(a)
        if k is not None:return constant(~k)
        if a[0]=='not':return a[1]
        if a[0] in {'and','or'}:return view(('or' if a[0]=='and' else 'and',('not',a[1]),('not',a[2])))
        return (op,a)
    if op in AC:
        items=[]
        def flatten(a):
            if a[0]==op:
                for x in a[1:]:flatten(x)
            else:items.append(a)
        for a in xs:flatten(a)
        boolean=op.startswith('bool');zero=FALSE if boolean else Z;ones=TRUE if boolean else T
        base=op.removeprefix('bool')
        if base=='and' and zero in items:return zero
        if base=='or' and ones in items:return ones
        neutral=ones if base=='and' else zero;items=[a for a in items if a!=neutral]
        if base in {'and','or'}:items=list(set(items))
        if base=='xor':items=[a for a in set(items) if items.count(a)%2]
        if not boolean:
            literals=[literal(a) for a in items if literal(a) is not None]
            items=[a for a in items if literal(a) is None]
            if literals:
                import functools,operator
                fn={'add':operator.add,'and':operator.and_,'or':operator.or_,'xor':operator.xor}[base]
                value=functools.reduce(fn,literals);k=constant(value)
                if base=='and' and k==Z:return Z
                if base=='or' and k==T:return T
                if k!=neutral:items.append(k)
        items.sort(key=repr)
        if not items:return neutral
        out=items[0]
        for a in items[1:]:out=(op,out,a)
        return out
    if op=='sub':
        a,b=xs
        if a==b:return Z
        if b==Z:return a
        if literal(a) is not None and literal(b) is not None:return constant(literal(a)-literal(b))
    if op=='mul':
        a,b=xs
        if Z in xs:return Z
        if ONE in xs:return b if a==ONE else a
        if literal(a) is not None and literal(b) is not None:return constant(literal(a)*literal(b))
        return (op,*sorted(xs,key=repr))
    return (op,*xs)


def context(guards):
    result=[]
    def add(p,t):
        p=view(p);p,pos=polarity(p);t=bool(t)==pos
        if (p[0]=='booland' and t) or (p[0]=='boolor' and not t):
            for x in p[1:]:add(x,t)
        else:result.append((p,t))
    for p,t in guards:add(p,t)
    return sorted(set(result),key=repr)


def substitute(e,old,new):
    if e==old:return new
    if e[0] in LEAVES:return e
    return view((e[0],*(substitute(x,old,new) for x in e[1:])))


def branch(e,guards,selector,truth):
    if selector[0]!='select' or selector not in order(e):raise ValueError('branch is not a source-view subterm')
    chosen=selector[2] if truth else selector[3]
    root=substitute(e,selector,chosen)
    ctx=[(substitute(p,selector,chosen),t) for p,t in guards]+[(selector[1],truth)]
    return root,context(ctx)


def source_view(e,guards):
    return view(e),context(guards)
