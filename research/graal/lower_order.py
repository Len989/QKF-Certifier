"""Exhaustive finite order gluing of sweep, successor and source outer branches."""
from carry_kernel import require,digest
NAMES=('zero','minimum','bound','greedy','successor','candidate','nonzero')

def weak_orders(n):
    if n==0:yield ();return
    for old in weak_orders(n-1):
        count=max(old,default=-1)+1
        for rank in range(count):yield old+(rank,)
        for rank in range(count+1):yield tuple(x+(x>=rank) for x in old)+(rank,)

def admissible(r,optional,can_zero):
    z,a,l,g,t,x,n=(r[k] for k in NAMES)
    if not(a<=x and l<=x):return False  # arbitrary feasible witness x
    if not can_zero and x==z:return False
    if a<z and l>z:return False  # explicit source-sign precondition
    # Native least-positive-mask-word lemma; only needed if a zero result is excluded.
    if x>z and not(z<n<=x):return False
    if a<l:
        if not optional:
            # No optional nonsign cell: each allowed sign slice is a singleton.
            if (x<z)==(a<z) and x!=a:return False
        else:
            if not(a<=g<=l and (a<z)==(g<z)):return False
            if g<l:
                # x >= l > g; universal successor gives g < t <= x.
                if not(g<t<=x):return False
                # If t is still in the same sign slice and <= l, the proved
                # greedy maximum would require t <= g, contradicting g < t.
                if (t<z)==(a<z) and t<=l:return False
    return True

def execute(ir,r,optional,can_zero):
    value=None;path=[];returned=False
    def run(code):
        nonlocal value,returned
        for node in code:
            op=node[0]
            if returned:return
            if op=='minimum':value=r['minimum'];path.append('minimum')
            elif op=='zero':value=r['zero'];path.append('no_optional_zero')
            elif op=='sweep':value=r['greedy'];path.append('greedy')
            elif op=='successor':value=r['successor'];path.append('successor')
            elif op=='if_below_bound':
                if value<r['bound']:run(node[1])
            elif op=='if_no_optional':run(node[2] if optional else node[1])
            elif op=='guarantee_le_bound':require(value<=r['bound'],'source guarantee in every admitted order')
            elif op=='exclude_zero':
                if value==r['zero'] and not can_zero:
                    require(r['candidate']>r['zero'],'positive witness for the native nonzero branch')
                    value=r['nonzero'];path.append('exclude_zero')
            elif op=='maximum_sentinel':value='MAX';path.append('maximum_sentinel')
            elif op=='return':returned=True
            else:raise ValueError('unknown outer IR')
    run(ir);require(returned,'complete source return')
    return value,path

CONCLUSION=dict(precondition='compatible masks, typed signed bound, and (lowerBound <= 0 or may-sign-bit = 0)',
    theorem='For every feasible mask/nonzero word x >= lowerBound, the source result R satisfies lowerBound <= R <= x. For empty carriers R >= lowerBound still follows from the exact final source guard.',
    consequence='Replacing only the lower bound by R preserves the complete joint word carrier for every additional upper bound.',
    precision='The source helper may return a bound below the exact minimum; no standalone exact-minimum theorem is claimed.',
    scope='All positive mathematical widths for the semantic lift; native Java widths 1..64, with production widths 1,8,16,32,64.')

def obligations(ir):
    total=0;accepted=0;paths={};records=[]
    for oid,order in enumerate(weak_orders(len(NAMES))):
        total+=1;r=dict(zip(NAMES,order))
        for optional in [False,True]:
            for zero in [False,True]:
                if not admissible(r,optional,zero):continue
                accepted+=1;value,path=execute(ir,r,optional,zero)
                require(type(value) is int and r['bound']<=value<=r['candidate'],'universal lower preservation order obligation')
                key='/'.join(path);paths[key]=paths.get(key,0)+1
                records.append([oid,int(optional),int(zero),value,path])
    return dict(weak_orders=total,flag_combinations=total*4,admitted_orders=accepted,paths=paths,obligations_sha256=digest(records))

def replay(ir,c):
    require(set(c)=={'schema','ir','obligations','conclusion'} and c['schema']=='qkf-lower-order-gluing-v1' and c['ir']==ir,'source outer certificate')
    expected=obligations(ir);require(c['obligations']==expected and c['conclusion']==CONCLUSION,'complete finite order evidence')
    return dict(status='proved_universal_conditional_lower_preservation',**expected)
