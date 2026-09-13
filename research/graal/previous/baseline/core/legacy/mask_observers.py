"""Checked compilation of bounded-count mask observations to existing runs.

No new transition node or concrete target is introduced. Numeric count grammar:
0, width, countl/r_{zero,one}, width-c, umin/umax(c,d), select(p,c,d), and
nonnegative literals <= the checked minimum width. Opposite-end raw counts
are rejected; complementing a count swaps the observed end.
"""
from functools import lru_cache
from qkf_certifier.kernel import children,at,replace,digest,Z,T,W,TRUE,FALSE
import observer_kernel as legacy

EXTENSION='qkf-bounded-count-observers-v1'
COUNTS={'countl_one','countl_zero','countr_one','countr_zero'}
MASKS={'set_low_bits','set_high_bits','clear_low_bits','clear_high_bits'}

@lru_cache(None)
def bounded(c,minimum):
    if minimum<1:return False
    if c in (Z,W):return True
    if c[0]=='const':return 0<=c[1]<=minimum
    if c[0] in COUNTS:return True
    if c[0]=='sub' and c[1]==W:return bounded(c[2],minimum)
    if c[0] in {'umin','umax'}:return bounded(c[1],minimum) and bounded(c[2],minimum)
    if c[0]=='select':return bounded(c[2],minimum) and bounded(c[3],minimum)
    return False

@lru_cache(None)
def mask(side,c,minimum):
    if side not in {'low','high'} or not bounded(c,minimum):raise ValueError('count bound not derived')
    if c==Z:return Z
    if c==W:return T
    if c[0]=='const':
        k=c[1]
        if side=='low':return Z if k==0 else ('const',(1<<k)-1)
        return legacy.high_window(k)
    if c[0] in COUNTS:
        matched=c[0].startswith('countr') if side=='low' else c[0].startswith('countl')
        if not matched:raise ValueError('numeric count observed at the opposite end')
        return ('set_'+side+'_bits',Z,c)
    if c[0]=='sub':return ('not',mask('high' if side=='low' else 'low',c[2],minimum))
    if c[0] in {'umin','umax'}:
        return ('and' if c[0]=='umin' else 'or',mask(side,c[1],minimum),mask(side,c[2],minimum))
    if c[0]=='select':return ('select',c[1],mask(side,c[2],minimum),mask(side,c[3],minimum))
    raise ValueError('unhandled bounded grammar')

def rewrite(e,minimum=2):
    if e[0] in MASKS:
        side='low' if e[0].endswith('low_bits') else 'high';m=mask(side,e[2],minimum)
        return ('or',e[1],m) if e[0].startswith('set') else ('and',e[1],('not',m))
    if e[0] in {'shl','lshr'} and e[1]==T:
        return ('not',mask('low' if e[0]=='shl' else 'high',e[2],minimum))
    raise ValueError('not a mask observation')

def step(root,path,rule,minimum):
    if rule=='mask:bounded-observation':
        old=at(root,path);new=rewrite(old,minimum)
        # Keep the existing primitive set-mask at zero as a terminal source
        # form, rather than cycling between it and OR(0, same-mask).
        if new==old or (old[0] in MASKS and old[1]==Z and old[0].startswith('set') and new==('or',Z,old)):
            raise ValueError('already a primitive mask')
        return replace(root,path,new)
    return legacy.step(root,path,rule,minimum)

def produce(initial,minimum=2,max_steps=10000):
    root=initial;trace=[]
    from qkf_certifier.kernel import RULES
    from guard_kernel import RULE_NAMES
    rules=('mask:bounded-observation',)+tuple('obs:'+r for r in legacy.RULE_NAMES)+tuple('guard:'+r for r in RULE_NAMES)+tuple('qkf:'+r for r in RULES)
    def attempt(path):
        nonlocal root
        for rule in rules:
            try:new=step(root,path,rule,minimum)
            except ValueError:continue
            trace.append({'path':list(path),'rule':rule,'before':digest(at(root,path)),'after':digest(at(new,path))});root=new
            if len(trace)>max_steps:raise RuntimeError('mask rewrite budget')
            return True
        return False
    def visit(path):
        while attempt(path):pass
        for i in children(at(root,path)):visit(path+[i])
        if attempt(path):visit(path)
    visit([]);return root,trace

def replay(initial,trace,expected,minimum=2):
    root=initial
    for s in trace:
        if digest(at(root,s['path']))!=s['before']:raise ValueError('mask before hash')
        root=step(root,s['path'],s['rule'],minimum)
        if digest(at(root,s['path']))!=s['after']:raise ValueError('mask after hash')
    if root!=expected:raise ValueError('mask result mismatch')
    return root
