"""Deterministic mechanism tests, exhaustive native checks and corruptions.

Generated during development, then frozen and rerun. Not an external holdout.
"""
import argparse,copy,itertools,json,random,time
from environment import ROOT,save
from corpus_io import load
from qkf_certifier.kernel import replace,digest
from regular_interfaces import tree,order
from symbolic_bridge import path_guards
from word_oracle import expr_value,kbwords
import result_kernel as K

X=('var',0);Y=('var',2);G=('cmp0',('var',1),K.Z)


def certificate(e,kind,parameter=None,guard=None,authority=None):
    root=e if guard is None else ('select',guard,e,K.Z);path=[] if guard is None else [2]
    guards=path_guards(root,path);after,p=K.derive(e,guards,kind,parameter,authority)
    final=replace(root,path,after)
    trace=[dict(schema=K.SCHEMA,minimum_width=2,path=path,kind=kind,parameter=parameter,guards=guards,
                before_hash=digest(root),after_hash=digest(final),after=after,proof=p)]
    K.replay(root,trace,final,authority)
    return root,final,trace


def dataset():
    out=[]
    masks=[K.S,('not',('clear_sign_bit',K.T)),('shl',K.ONE,('sub',K.W,K.ONE)),('set_sign_bit',('xor',X,X))]
    for denominator in ['free','negative','positive','selected']:
        d=Y if denominator=='free' else ('or',Y,K.S) if denominator=='negative' else ('clear_sign_bit',Y) if denominator=='positive' else ('select',G,('set_sign_bit',Y),Y)
        for form,S in enumerate(masks):
            q=('sdiv',('add',X,K.Z) if form%2 else X,d)
            words=[('mask',('and',S,q)),('reversed-mask',('and',q,S)),
                   ('negative-test',('cmp2',q,K.Z)),('nonnegative-test',('cmp5',q,K.Z)),
                   ('logical-extract',('lshr',q,('sub',K.W,K.ONE))),
                   ('signed-fill',('ashr',q,('sub',K.W,K.ONE))),
                   ('complement',('and',S,('not',q))),
                   ('composite',('and',S,('xor',q,X)))]
            for name,e in words:out.append(dict(name=f'sdiv/{denominator}/{name}/{form}',expression=e,kind='sign'))
    high=[('set_high_bits',K.Z,Y),('not',('set_low_bits',K.Z,Y)),('clear_low_bits',K.T,Y),('shl',K.T,Y),
          ('set_sign_bit',Y),('umax',K.S,Y),('select',G,('set_high_bits',K.Z,Y),K.Z),
          ('or',('shl',K.T,Y),('set_high_bits',K.Z,X)),
          ('and',('shl',K.T,Y),('set_high_bits',K.Z,X))]
    for i,d in enumerate(high):
        for op in ['urem','udiv']:
            for form in range(4):
                divisor=d if form==0 else ('or',K.Z,d) if form==1 else ('sub',('add',d,K.ONE),K.ONE) if form==2 else ('not',('not',d))
                out.append(dict(name=f'high-divisor/{i}/{op}/{form}',expression=(op,X,divisor),kind='division-action'))
    # Every action consumer, several source-selected amounts, both branch polarities.
    for op in sorted(K.ACTION.SHIFTS | K.ACTION.MASKS):
        for family in ['negative-binary','width-or-zero','one-minus-one-or-width']:
            for form in range(4):
                g=G if form<2 else ('cmp1',('var',1),K.Z)
                if family=='negative-binary':
                    s=('select',g,K.Z,K.ONE) if form<2 else ('select',g,K.ONE,K.Z);n=('sub',K.Z,s)
                elif family=='width-or-zero':
                    s=('select',g,K.W,K.Z) if form<2 else ('select',g,K.Z,K.W);n=s
                else:
                    s=('select',g,K.ONE,K.W) if form<2 else ('select',g,K.W,K.ONE);n=('sub',K.ONE,s)
                if form%2:n=('sub',('add',n,K.ONE),K.ONE)
                out.append(dict(name=f'action/{op}/{family}/{form}',expression=(op,X,n),kind='action-on-word',parameter=dict(selector=K.native(s))))
    for op in ['countl_zero','countl_one']:
        for form in range(4):
            carrier=Y if op=='countl_zero' else ('not',Y)
            payload=('and',X,('not',carrier))
            if form%2:payload=('and',('not',carrier),X)
            n=(op,Y);word=('shl',payload,n)
            e=('and',masks[form],word) if form<2 else ('cmp2',word,K.Z)
            out.append(dict(name=f'aligned/{op}/{form}',expression=e,kind='sign'))
    for op in ['lshr','ashr']:
        for amount in [Y,('countr_zero',Y),('countl_one',Y),('width',)]:
            out.append(dict(name=f'shift-sign/{op}/{repr(amount)}',expression=('and',K.S,(op,X,amount)),kind='sign'))
    for op in ['srem','sdiv','urem','udiv']:
        out.append(dict(name=f'unit-word/{op}',expression=(op,X,('clear_sign_bit',K.ONE)),kind='word'))
    return out


def run(out):
    start=time.perf_counter();rng=random.Random(2026091302);records=[];data=dataset()
    save(out/'DATASET.json',data)
    for case in data:
        e=tree(case['expression']);param=case.get('parameter')
        root,final,trace=certificate(e,case['kind'],param);checks=0
        for w in (2,3,4):
            for a,b in itertools.product(range(1<<w),repeat=2):
                for selector in (0,1):
                    values=[a,selector,b,0]
                    assert expr_value(root,values,w)==expr_value(final,values,w),(case['name'],w,values)
                    checks+=1
        for w in (8,16,32,64,128,256):
            for _ in range(16):
                values=[rng.getrandbits(w),rng.randrange(2),rng.getrandbits(w),0]
                assert expr_value(root,values,w)==expr_value(final,values,w),(case['name'],w,values)
                checks+=1
        records.append(dict(name=case['name'],source=root,final=final,trace=trace,checks=checks))
    # Complete two-word domains through width 8 for the total signed quotient row.
    e=('and',K.S,('sdiv',X,Y));root,final,trace=certificate(e,'sign');exhaustive=0
    for w in range(2,9):
        for a,b in itertools.product(range(1<<w),repeat=2):
            values=[a,0,b,0]
            assert expr_value(root,values,w)==expr_value(final,values,w),(w,values)
            exhaustive+=1
    high_guard=('boolor',('cmp0',Y,K.Z),('cmp2',Y,K.Z));high_exhaustive=0;high_examples=[]
    for op in ['urem','udiv']:
        sr,fr,tr=certificate((op,X,Y),'division-action',guard=high_guard)
        high_examples.append((sr,fr,tr))
        for w in range(2,9):
            for a in range(1<<w):
                for b in [0]+list(range(1<<(w-1),1<<w)):
                    values=[a,0,b,0]
                    assert expr_value(sr,values,w)==expr_value(fr,values,w),(op,w,values)
                    high_exhaustive+=1
    # Actual contract and guard jointly force the absent aligned payload bit.
    bundle,_,_=load('KnownBits_Add');scope=K.source_authority(bundle,'partial_solution_12')
    guard=('cmp0',('var',0),('not',('var',2)))
    expr=('cmp2',('shl',('var',1),('countl_zero',('var',3))),K.Z)
    scoped,scoped_final,scoped_trace=certificate(expr,'sign',guard=guard,authority=scope)
    assert scoped_trace[0]['after']==K.FALSE
    contextual_checks=0
    for w in (2,3,4):
        for a,b in itertools.product(kbwords(w),repeat=2):
            values=a+b
            assert expr_value(scoped,values,w)==expr_value(scoped_final,values,w),(w,values)
            contextual_checks+=1
    rejected=[]
    def reject(name,source,t,target,authority=None):
        try:K.replay(source,t,target,authority)
        except (ValueError,KeyError,IndexError,TypeError) as ex:rejected.append(dict(name=name,reason=str(ex)));return
        raise AssertionError('corruption accepted: '+name)
    for i,r in enumerate(records):
        t=copy.deepcopy(r['trace']);t[0]['proof']['interface']['value']=('false-value',)
        reject(r['name']+'/interface',tree(r['source']),t,tree(r['final']))
    for name,mutate in [
        ('remove-overflow-cell',lambda t:t[0]['proof']['interface']['steps'][-1]['cells'].pop(2)),
        ('wrong-width',lambda t:t[0].update(minimum_width=1)),
        ('wrong-output',lambda t:t[0].update(after=K.Z)),
        ('wrong-query',lambda t:t[0].update(kind='word')),
        ('wrong-source-binding',lambda t:t[0].update(before_hash='0'*64)),
    ]:
        t=copy.deepcopy(trace);mutate(t);reject(name,root,t,final)
    reject('missing-contract',scoped,scoped_trace,scoped_final,None)
    altered=copy.deepcopy(scope);altered['entry']='partial_solution_0'
    reject('different-source-authority',scoped,scoped_trace,scoped_final,altered)
    for name,other in [('remove-path-guard',expr),('reverse-path-guard',('select',guard,K.Z,expr))]:
        t=copy.deepcopy(scoped_trace);path=[] if name=='remove-path-guard' else [3]
        t[0].update(path=path,guards=path_guards(other,path),before_hash=digest(other))
        target=replace(other,path,K.FALSE);t[0]['after_hash']=digest(target)
        reject(name,other,t,target,scope)
    for op,(sr,fr,tr) in zip(['urem','udiv'],high_examples):
        e2=(op,X,Y);t=copy.deepcopy(tr)
        t[0].update(path=[],guards=[],before_hash=digest(e2),after_hash=digest(t[0]['after']))
        reject('high-divisor-missing-guard/'+op,e2,t,tree(t[0]['after']))
    # High-divisor property is not assumed for arbitrary or lower masks.
    refusals=[]
    for name,d in [('arbitrary',Y),('low-mask',('set_low_bits',K.Z,Y)),('xor-high',('xor',('set_sign_bit',X),('set_sign_bit',Y)))]:
        try:certificate(('urem',X,d),'division-action')
        except ValueError as ex:refusals.append(dict(name=name,reason=str(ex)))
        else:raise AssertionError(name)
    separators=[]
    for name,before,after,values,w in [
        ('zero-quotient',('and',K.S,('sdiv',X,Y)),('select',('boolxor',('cmp2',X,K.Z),('cmp2',Y,K.Z)),K.S,K.Z),[1,0,6,0],3),
        ('MIN-overflow',('and',K.S,('sdiv',X,Y)),K.Z,[4,0,7,0],3),
        ('total-zero-divisor',('and',K.S,('sdiv',X,Y)),K.Z,[1,0,0,0],3),
        ('non-high-remainder',('urem',X,Y),('select',('cmp9',X,Y),('sub',X,Y),X),[7,0,2,0],3),
        ('removed-alignment',('cmp2',('shl',X,('countl_zero',Y)),K.Z),K.FALSE,[4,0,4,0],3),
    ]:
        a=expr_value(before,values,w);b=expr_value(after,values,w);assert a!=b
        separators.append(dict(name=name,width=w,values=values,before=before,after=after,before_value=a,after_value=b))
    result=dict(status='passed',cases=len(records),representation_checks=sum(r['checks'] for r in records),
                exhaustive_signed_division_checks=exhaustive,contextual_checks=contextual_checks,
                exhaustive_high_divisor_checks=high_exhaustive,
                corruptions_rejected=len(rejected),refusals=refusals,separating_inputs=separators,
                records=records,rejections=rejected,contextual=dict(source=scoped,final=scoped_final,trace=scoped_trace),
                seconds=time.perf_counter()-start)
    save(out/'results.json',result)
    return {k:result[k] for k in ['status','cases','representation_checks','exhaustive_signed_division_checks','exhaustive_high_divisor_checks','contextual_checks','corruptions_rejected','seconds']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=ROOT/a.output
    out.mkdir(parents=True,exist_ok=False);print(json.dumps(run(out)))
