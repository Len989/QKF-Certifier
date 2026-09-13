"""Source-bound observation factors for boundary masks and word actions.

Trusted local semantic rules, finite supplied tables and affine bounds only.
No solver, invariant discovery, candidate enumeration or path search imports.
"""
import itertools
from qkf_certifier.kernel import Z,T,W,digest,at,replace
from regular_interfaces import tree,order
from symbolic_bridge import path_guards
from semantic_view import view,constant,LEAVES
import action_kernel as A
import semantic_choice_kernel as OLD

SCHEMA='qkf-boundary-action-v1'
ONE=('const',1)
COUNTS=A.COUNTS;ACTIONS=A.SHIFTS|A.MASKS
LABELS=['empty','proper','full']
MOD=(1,0,0);ZERO=(0,0,0);WIDTH=(0,1,0);UNIT=(0,0,1)
MAX_COUNTS=4;TAIL=3


def add(a,b):return tuple(x+y for x,y in zip(a,b))
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def scale(a,k):return tuple(k*x for x in a)
def value(v,w):return v[0]*(1<<w)+v[1]*w+v[2]


def native(e):
    e=view(tree(e))
    if e[0] in LEAVES:return e
    xs=tuple(native(x) for x in e[1:]);e=(e[0],*xs)
    if e[0] in COUNTS and e[1][0]=='not':
        op=e[0].replace('one','TEMP').replace('zero','one').replace('TEMP','zero')
        return (op,e[1][1])
    return view(e)


def counts(e):
    found=set()
    def walk(t):
        if t[0] in COUNTS:found.add(t);return
        if t[0] not in LEAVES:
            for c in t[1:]:walk(c)
    walk(e)
    result=sorted(found,key=repr)
    if len(result)>MAX_COUNTS:raise ValueError('boundary count budget')
    return result


def observation(n):
    if n[0] not in COUNTS:raise ValueError('not a native count')
    side='low' if n[0].startswith('countr') else 'high'
    desired=int(n[0].endswith('one'));rows=[]
    for state,bit in itertools.product((0,1),repeat=2):
        out=state*int(bit==desired)
        rows.append(dict(adjacent_prefix=state,word_bit=bit,prefix=out))
    return dict(count=n,word=n[1],name=digest(n),side=side,desired=desired,
        protected_bits=[0,1],supplied_cells=rows,
        equation='p[i+1] = p[i] & match(x[i])' if side=='low' else 'h[i] = match(x[i]) & h[i+1]',
        endpoint='p[0]=1' if side=='low' else 'h[w]=1',
        empty=A.count_zero(n),full=A.count_full(n),count_range=[0,'w'])


class Bounds:
    """Exponential-affine intervals in one fixed endpoint cell.

    The supplied count cell guarantees its interval. Every comparison used
    below is either evaluated at the exceptional width or proved by induction.
    """
    def __init__(self,domains,fixed=None):
        self.domains=domains;self.fixed=fixed;self.steps=[];self.memo={};self.checks=[]
    def ge(self,a,b,strict=False):
        d=sub(sub(a,b),UNIT if strict else ZERO)
        if self.fixed is not None:
            if value(d,self.fixed)<0:return False
            self.checks.append(dict(difference=d,width=self.fixed,value=value(d,self.fixed)));return True
        try:p=A.ge_zero(d,TAIL)
        except ValueError:return False
        self.checks.append(p);return True
    def lesser(self,a,b):
        if self.ge(b,a):return a
        if self.ge(a,b):return b
        raise ValueError('boundary interval endpoints cross on the tail')
    def greater(self,a,b):
        if self.ge(a,b):return a
        if self.ge(b,a):return b
        raise ValueError('boundary interval endpoints cross on the tail')
    def canonical(self,lo,hi):
        if self.fixed is not None:
            l,h=value(lo,self.fixed),value(hi,self.fixed);m=1<<self.fixed
            if l//m!=h//m:raise ValueError('exceptional modular interval straddles zero')
            return (0,0,l%m),(0,0,h%m)
        for k in range(-4,5):
            l,h=sub(lo,scale(MOD,k)),sub(hi,scale(MOD,k))
            if self.ge(l,ZERO) and self.ge(sub(MOD,UNIT),h):return l,h
        raise ValueError('modular interval has no single checked representative')
    def boolean(self,e):
        if e==('true',):return True
        if e==('false',):return False
        if e[0] in {'booland','boolor','boolxor'}:
            a,b=self.boolean(e[1]),self.boolean(e[2])
            if e[0]=='booland' and (a is False or b is False):return False
            if e[0]=='boolor' and (a is True or b is True):return True
            if a is None or b is None:return None
            return {'booland':a and b,'boolor':a or b,'boolxor':a!=b}[e[0]]
        if e[0] not in {'cmp0','cmp6'}:return None
        try:a,b=self.word(e[1]),self.word(e[2])
        except ValueError:return None
        if e[0]=='cmp0':
            if a[0]==a[1]==b[0]==b[1]:return True
            if self.ge(a[0],b[1],True) or self.ge(b[0],a[1],True):return False
        else:
            if self.ge(b[0],a[1],True):return True
            if self.ge(a[0],b[1]):return False
        return None
    def word(self,e):
        if e in self.memo:return self.memo[e]
        op=e[0];rule=op
        if e in self.domains:out=self.domains[e];rule='supplied-count-cell'
        elif e==W:out=((0,0,self.fixed),)*2 if self.fixed is not None else (WIDTH,WIDTH)
        elif e in {Z,T} or op=='const':
            k=0 if e==Z else -1 if e==T else e[1]
            out=self.canonical((0,0,k),(0,0,k))
        elif op in {'add','sub'}:
            a,b=self.word(e[1]),self.word(e[2])
            out=self.canonical(add(a[0],b[0]),add(a[1],b[1])) if op=='add' else self.canonical(sub(a[0],b[1]),sub(a[1],b[0]))
        elif op=='select':
            p=e[1]
            # The native semantic form exposes unsigned min/max as select.
            if p[0]=='cmp6' and (e[2:]==p[1:] or e[2:]==tuple(reversed(p[1:]))):
                a,b=self.word(p[1]),self.word(p[2]);is_min=e[2:]==p[1:]
                fn=self.lesser if is_min else self.greater
                out=(fn(a[0],b[0]),fn(a[1],b[1]));rule='unsigned-min' if is_min else 'unsigned-max'
            else:
                truth=self.boolean(p)
                if truth is not None:out=self.word(e[2] if truth else e[3]);rule='determined-selection'
                else:
                    a,b=self.word(e[2]),self.word(e[3]);out=(self.lesser(a[0],b[0]),self.greater(a[1],b[1]));rule='selection-cover'
        else:raise ValueError('scalar boundary grammar: '+op)
        self.steps.append(dict(source_hash=digest(e),rule=rule,interval=out));self.memo[e]=out;return out
    def action(self,op,x,bounds):
        lo,hi=bounds;w=(0,0,self.fixed) if self.fixed is not None else WIDTH
        if self.ge(lo,w):return A.action_expression(op,x,('saturated',)),dict(kind='saturated',lower=lo)
        if lo==hi and lo[:2]==(0,0) and 0<=lo[2]<=8:
            return A.action_expression(op,x,('constant',lo[2])),dict(kind='constant',value=lo[2])
        if lo==hi==sub(w,UNIT):
            sign=('set_sign_bit',Z)
            if op=='lshr':out=A.action_expression(op,x,('top-bit',))
            elif op=='ashr':out=A.signfill(x)
            elif op=='shl':out=('select',('cmp1',('and',x,ONE),Z),sign,Z)
            else:
                mask=('not',sign) if op.endswith('low_bits') else ('not',ONE)
                out=('or',x,mask) if op.startswith('set') else ('and',x,('not',mask))
            return out,dict(kind='all-but-one-position',operation=op)
        raise ValueError('endpoint observation does not determine a supported action')


def cell_domains(ns,labels,fixed=None):
    w=(0,0,fixed) if fixed is not None else WIDTH
    return {n: [(ZERO,ZERO),(UNIT,sub(w,UNIT)),(w,w)][LABELS.index(label)] for n,label in zip(ns,labels)}


def emit(ns,cells,index=0,prefix=()):
    if index==len(ns):return cells[prefix]
    empty,proper,full=[emit(ns,cells,index+1,prefix+(label,)) for label in LABELS]
    return native(('select',A.count_zero(ns[index]),empty,('select',A.count_full(ns[index]),full,proper)))


def endpoint_action(e):
    op,x,amount=e
    ns=counts(amount)
    if not ns:raise ValueError('no count observation requested')
    records=[];outputs={}
    for labels in itertools.product(LABELS,repeat=len(ns)):
        phases=[];phase_outputs=[]
        for fixed in [2,None]:
            domains=cell_domains(ns,labels,fixed);b=Bounds(domains,fixed)
            interval=b.word(amount);out,action=b.action(op,x,interval)
            phases.append(dict(width=fixed or 'all w>=3',count_intervals=[domains[n] for n in ns],
                scalar_steps=b.steps,inequalities=b.checks,action=action));phase_outputs.append(out)
        small,tail=phase_outputs
        outputs[labels]=native(small if small==tail else ('select',A.width_is(2),small,tail))
        records.append(dict(labels=labels,phases=phases,output=outputs[labels]))
    out=emit(ns,outputs)
    return out,dict(kind='endpoint-action-factor',observations=[observation(n) for n in ns],
        exhaustive_labels=LABELS,cells=records,minimum_width=2,tail_start=3)


def affine(e,n):
    if e==n:return (0,1,0)
    if e==W:return (1,0,0)
    if e in {Z,T}:return (0,0,0 if e==Z else -1)
    if e[0]=='const':return (0,0,e[1])
    if e[0] in {'add','sub'}:
        a,b=affine(e[1],n),affine(e[2],n)
        return add(a,b) if e[0]=='add' else sub(a,b)
    raise ValueError('position amount is not affine in one count')


def position_action(e):
    op,x,amount=e;ns=counts(amount)
    if len(ns)!=1:raise ValueError('position factor requires one named count')
    n=ns[0];desc=observation(n);side=desc['side'];coeff=affine(amount,n);a,b,d=coeff
    if d not in {-1,0,1} or (a,b) not in {(0,1),(1,-1)}:raise ValueError('unsupported boundary offset')
    if op in A.MASKS:target_side='low' if op.endswith('low_bits') else 'high'
    elif op in {'shl','lshr'} and x==T:target_side='low' if op=='shl' else 'high'
    else:raise ValueError('position factor does not compile arbitrary word relocation')
    direct=(a,b)==(0,1)
    if (side==target_side)!=direct:raise ValueError('boundary observed at incompatible end')
    p=('set_'+side+'_bits',Z,n)
    edge=ONE if side=='low' else ('set_sign_bit',Z)
    extend=('or',('shl' if side=='low' else 'lshr',p,ONE),edge)
    shrink=('lshr' if side=='low' else 'shl',p,ONE)
    if direct:
        mask=p if d==0 else extend if d==1 else ('select',desc['empty'],T,shrink)
    else:
        mask=('not',p) if d==0 else ('not',shrink) if d==1 else ('select',desc['full'],T,('not',extend))
    if op in A.SHIFTS:out=('not',mask)
    else:out=('or',x,mask) if op.startswith('set') else ('and',x,('not',mask))
    proof=dict(kind='position-action-factor',observation=desc,affine_amount=coeff,target_side=target_side,
        prefix=p,extended_prefix=extend,shortened_prefix=shrink,mask=mask,
        laws=['one-position-extension','one-position-restriction','opposite-end-complement','negative-one-saturates'],
        no_positive_wrap=A.ge_zero((1,-1,-2),2),negative_one_is_saturated=A.ge_zero((1,-1,-1),2),minimum_width=2)
    return native(out),proof


def derive(e,guards,engine):
    e=tree(e);original=e;e=native(e)
    if e[0] not in ACTIONS:raise ValueError('not a boundary action consumer')
    if len(order(e[2]))>128:raise ValueError('boundary amount DAG budget')
    if engine=='endpoints':after,proof=endpoint_action(e)
    elif engine=='position':after,proof=position_action(e)
    else:raise ValueError('boundary engine')
    return after,dict(source_hash=digest(original),guards_hash=digest(guards),view_hash=digest(e),
        kind=proof['kind'],derivation=proof,after_hash=digest(after),minimum_width=2)


def proof_steps(proof):
    if proof['kind'] not in {'endpoint-action-factor','position-action-factor'}:return OLD.proof_steps(proof)
    def count(v):
        if isinstance(v,dict):return 1+sum(count(x) for x in v.values())
        if isinstance(v,(list,tuple)):return sum(count(x) for x in v)
        return 0
    return count(proof)


def replay(initial,trace,expected):
    root=tree(initial)
    if len(trace)>1000:raise ValueError('boundary rewrite budget')
    steps=0
    for t in trace:
        if t['schema']!=SCHEMA:
            nxt=replace(root,t['path'],tree(t['after']));root,n=OLD.replay(root,[t],nxt);steps+=n;continue
        if t['minimum_width']!=2 or t['before_hash']!=digest(root):raise ValueError('boundary source binding')
        g=path_guards(root,t['path']);after,proof=derive(at(root,t['path']),g,t['engine'])
        if digest(g)!=digest(t['guards']) or digest(proof)!=digest(t['proof']) or after!=tree(t['after']):raise ValueError('boundary derivation mismatch')
        root=replace(root,t['path'],after);steps+=proof_steps(proof)
        if digest(root)!=t['after_hash']:raise ValueError('boundary result binding')
    if root!=tree(expected):raise ValueError('boundary final expression')
    return root,steps
