"""Cross-consumer tests of named source rows, sparse words and payload actions."""
import argparse,copy,itertools,json,random,time
from environment import ROOT,save
from qkf_certifier.kernel import digest,replace
from regular_interfaces import tree
from symbolic_bridge import path_guards
from word_oracle import expr_value,kbwords
import context_kernel as K
from context_producer import candidates
from validate_context import authority


def make(e,parameter,guard=None,scope=None):
    root=e if guard is None else ('select',guard,e,K.Z);path=[] if guard is None else [2]
    guards=path_guards(root,path);after,proof=K.derive(e,guards,scope,parameter)
    final=replace(root,path,after)
    trace=[dict(schema=K.SCHEMA,minimum_width=2,policy='guards' if scope is None else 'context',path=path,
        parameter=parameter,guards=guards,before_hash=digest(root),after_hash=digest(final),after=after,proof=proof)]
    K.replay(root,trace,final,scope)
    return root,final,trace


def suite(out):
    start=time.perf_counter();records=[];rejects=[];separators=[];rng=random.Random(18731)
    x,y,p=('var',2),('var',3),('var',0)
    def record(name,e,param,guard=None,scope=None):
        root,final,trace=make(e,param,guard,scope);checks=0
        for w in (2,3,4,5):
            for a,b in itertools.product(range(1<<w),repeat=2):
                values=[a,0,b,0]
                assert expr_value(root,values,w)==expr_value(final,values,w),(name,w,values)
                checks+=1
        for w in (8,16,32,64,128,256):
            for _ in range(32):
                values=[rng.getrandbits(w),0,rng.getrandbits(w),0]
                assert expr_value(root,values,w)==expr_value(final,values,w),(name,w,values)
                checks+=1
        records.append(dict(name=name,source=root,final=final,trace=trace,checks=checks))
    # 4 order choices x 2 remainder consumers x 4 presentations.
    for selection in ('smin','smax','umin','umax'):
        v=K.native((selection,K.Z,x))
        # A native unsigned min/max with zero may still be represented as select.
        for rem in ('urem','srem'):
            for form in range(4):
                selected=(selection,K.Z,x) if form==0 else v if form==1 else (selection,x,K.Z) if form==2 else ('add',(selection,x,K.Z),K.Z)
                e=(rem,selected,x);selectors=[t for t in K.order(K.native(e)) if t[0]=='select']
                assert selectors
                record(f'source-choice/{selection}/{rem}/{form}',e,dict(selector=selectors[0]))
    # The existing lower-boundary bridge feeds both run counts and remainders.
    for kind in ('first-zero','first-one','unit-shift'):
        for form in range(4):
            plus=[('add',x,K.ONE),('sub',x,('const',-1)),('sub',('add',x,('const',3)),('const',2)),('add',K.ONE,('add',x,K.Z))][form]
            neg=[('sub',K.Z,x),('sub',('const',3),('add',x,('const',3))),('sub',K.Z,('add',x,K.Z)),('sub',('sub',K.ONE,x),K.ONE)][form]
            d=('and',('not',x),plus) if kind=='first-zero' else ('and',x,neg) if kind=='first-one' else ('shl',K.ONE,('add',x,K.Z) if form%2 else x)
            if form%2 and kind!='unit-shift':d=(d[0],d[2],d[1])
            prem=next(candidates(K.native(d),[]))
            record(f'sparse/{kind}/urem/{form}',('urem',p,d),dict(sparse_divisor=prem))
            for op in ('countl_one','countr_one'):
                n=(op,d);record(f'sparse/{kind}/{op}/{form}',n,dict(count=n,premises=prem))
    # Relational action: the count can range up to w. No binary count claim.
    for form in range(4):
        d=('add',x,K.ONE) if form%2==0 else ('sub',x,('const',-1))
        carrier=('and',('not',x),d)
        payload=('and',p,carrier) if form<2 else ('and',carrier,('and',p,K.T))
        n=('countr_one',d) if form%2==0 else ('countr_zero',('not',d))
        record(f'payload/free-boundary/{form}',('lshr',payload,n),dict(observed_action='lowest-set-bit-erasure'))
    # The same action obtained from the actual KnownBits pair, with no explicit complement.
    scope=authority();d=('add',('var',0),K.ONE);payload=('and',('var',1),('and',x,d))
    e=('lshr',payload,('countr_one',d));param=dict(observed_action='lowest-set-bit-erasure')
    root,final,trace=make(e,param,scope=scope);count=0
    for w in (2,3,4):
        for a,b in itertools.product(kbwords(w),repeat=2):
            values=a+b;assert expr_value(root,values,w)==expr_value(final,values,w);count+=1
    records.append(dict(name='payload/contract',source=root,final=final,trace=trace,checks=count))
    # Malformed or unjustified interfaces must fail even if root hashes are rebound.
    bad=[
        ('arbitrary-divisor',('urem',p,x),dict(sparse_divisor=dict(unit_shift=x)),None),
        ('wrong-boundary',('urem',p,('or',('not',x),('add',x,K.ONE))),dict(sparse_divisor=dict(boundary_count=('countr_one',x))),None),
        ('payload-without-support',('lshr',p,('countr_one',x)),param,None),
        ('payload-without-contract',e,param,None),
        ('wrong-direction',('shl',payload,('countr_one',d)),param,scope),
        ('wrong-run',('lshr',payload,('countr_zero',d)),param,scope),
    ]
    for name,e2,par,auth in bad:
        try:make(e2,par,scope=auth)
        except ValueError as ex:rejects.append(dict(name=name,reason=str(ex)))
        else:raise AssertionError(name)
    for r in records:
        t=copy.deepcopy(r['trace']);proof=t[0]['proof']
        if 'supplied_cells' in proof:
            proof['supplied_cells'][0]['forged']=True
            try:K.replay(tree(r['source']),t,tree(r['final']),scope if r['name']=='payload/contract' else None)
            except ValueError:rejects.append(dict(name=r['name']+'/corrupt-cell'))
            else:raise AssertionError(r['name'])
    for name,e2,a2,values,w in [
        ('nonsparse-remainder',('urem',p,x),('and',p,('sub',x,K.ONE)),[3,0,3,0],2),
        ('missing-payload-relation',('lshr',p,('countr_one',x)),('select',('cmp0',('and',x,K.ONE),K.Z),p,K.Z),[3,0,1,0],2),
        ('general-count-is-not-binary',('countr_one',x),('select',('cmp1',('and',x,K.ONE),K.Z),K.ONE,K.Z),[0,0,7,0],3),
    ]:
        before=expr_value(e2,values,w);after=expr_value(a2,values,w);assert before!=after
        separators.append(dict(name=name,width=w,values=values,before=e2,after=a2,before_value=before,after_value=after))
    summary=dict(status='passed',cases=len(records),finite_random_checks=sum(r['checks'] for r in records),
                 rejected=len(rejects),records=records,rejections=rejects,separating_inputs=separators,
                 seconds=time.perf_counter()-start)
    save(out/'results.json',summary)
    return {k:summary[k] for k in ['cases','finite_random_checks','rejected','seconds']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
    out=ROOT/a.output;out.mkdir(parents=True,exist_ok=False);print(json.dumps(suite(out)))
