"""Declared observation tasks with independently specified finite images.

No corpus-name dispatch. Variants are ordinary native identities and guarded
compositions. These are metamorphic tests, not unseen external benchmarks.
"""
from semantic_view import constant
A=('var',0);B=('var',1);C=('var',2);Z=('zero',);ONE=('const',1);T=('ones',);TRUE=('true',)


def neg(p):return ('boolxor',p,TRUE)


def variants(e):
    """Neutral presentation changes, applied without the semantic-view code."""
    def commute(t):
        if t[0] in {'var','const','zero','ones','width','true','false'}:return t
        xs=tuple(commute(x) for x in t[1:])
        if t[0] in {'and','or','xor','add','mul','umin','umax','smin','smax'}:xs=tuple(reversed(xs))
        return (t[0],*xs)
    return [e,commute(e),('add',Z,e),('not',('not',e))]


def cases():
    result=[]
    def add(family,forms,expected,guards=()):
        seen=set()
        for f in forms:
            for expr in variants(f):
                key=(expr,tuple(guards))
                if key in seen:continue
                seen.add(key);result.append(dict(id=family+'__'+str(len(seen)).zfill(2),family=family,expression=expr,guards=list(guards),expected=expected))
    for k in [1,2,3]:
        x=constant(k)
        add('unsigned_cap_'+str(k),[('umin',A,x),('select',('cmp6',A,x),A,x),('select',('cmp7',A,x),A,x),
            ('select',('cmp9',A,x),x,A),('select',('cmp8',x,A),A,x)],list(range(k+1)))
    for kind,lo,hi in [('s',-1,1),('s',-2,1),('s',0,1),('u',1,2),('u',2,3)]:
        l,h=constant(lo),constant(hi);lt='cmp2' if kind=='s' else 'cmp6';gt='cmp4' if kind=='s' else 'cmp8'
        forms=[(kind+'max',l,(kind+'min',A,h)),(kind+'min',h,(kind+'max',A,l)),
           ('select',(lt,A,l),l,('select',(gt,A,h),h,A))]
        add('clamp_'+kind+'_'+str(lo)+'_'+str(hi),forms,list(range(lo,hi+1)))
    for k in [1,3]:
        c=constant(k);q=('and',A,c);dual=('not',('or',('not',A),('not',c)))
        add('shared_double_'+str(k),[('add',q,q),('add',dual,q)],list(range(0,2*k+1,2)))
    q=('and',A,constant(3));r=('not',('or',('not',A),('not',constant(3))))
    add('shared_polynomial',[('sub',('mul',q,q),q),('sub',('mul',r,q),r)],[0,2,6])
    add('shared_product_complement',[('mul',q,('sub',constant(3),q)),('mul',r,('sub',constant(3),q))],[0,2])
    add('shared_xor_complement',[('xor',q,('sub',constant(3),q)),('xor',r,('sub',constant(3),q))],[3])
    p=('cmp6',A,B)
    add('complementary_cells',[('add',('select',p,Z,ONE),('select',neg(p),Z,ONE)),
        ('add',('select',('cmp9',A,B),ONE,Z),('select',('cmp7',B,A),Z,ONE))],[1])
    for index,guards in enumerate([
      [(('cmp7',A,B),True),(('cmp7',B,ONE),True)],
      [(('cmp9',B,A),True),(('cmp9',ONE,B),True)],
      [(('booland',('cmp7',A,B),('cmp7',B,ONE)),True)],
      [(('cmp0',A,B),True),(('cmp7',B,ONE),True)],
      [(('cmp7',A,B),True),(('cmp7',B,C),True),(('cmp7',C,ONE),True)]
    ]):add('guard_chain_'+str(index),[A],[0,1],guards)
    add('signed_guard_chain',[A],[0,1],[(('cmp3',A,B),True),(('cmp3',B,ONE),True),(('cmp5',A,Z),True)])
    add('empty_order_cell',[A],[],[(('cmp6',A,B),True),(('cmp7',B,A),True)])
    add('empty_unsigned_boundary',[A],[],[(('cmp6',A,Z),True)])
    return result
