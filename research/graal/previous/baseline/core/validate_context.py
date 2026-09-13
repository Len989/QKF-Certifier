"""Local bridge checks, representation protocol, and adversarial replay tests.

These generated cases are development-designed mechanism tests, not an external
holdout or all-width proofs. All-width justification lives in the small checker.
"""
import argparse
import copy
import itertools
import json
import random
import time
from environment import ROOT, save
from corpus_io import load
from qkf_certifier.kernel import digest, replace
from regular_interfaces import tree
from symbolic_bridge import path_guards
from word_oracle import expr_value, kbwords as valid_masks
import context_kernel as K
from context_producer import candidates


def authority():
    bundle,_,_=load('KnownBits_UaddSat')
    return K.source_authority(bundle,'partial_solution_10')


def certify(root, path, scope, policy):
    guards=path_guards(root,path);e=K.at(root,path);failures=[]
    for n in [n for n in K.order(K.native(e)) if n[0] in K.COUNTS]:
        for premises in candidates(n[1],guards):
            parameter=dict(count=n,premises=premises)
            try:after,proof=K.derive(e,guards,scope,parameter)
            except ValueError as ex:
                failures.append(str(ex));continue
            final=replace(root,path,after)
            trace=[dict(schema=K.SCHEMA,minimum_width=2,policy=policy,path=path,guards=guards,
                        parameter=parameter,before_hash=digest(root),after_hash=digest(final),
                        after=after,proof=proof)]
            K.replay(root,trace,final,scope)
            return final,trace
    raise ValueError('no scoped cover: '+repr(sorted(set(failures))))


def dataset():
    records=[]
    operations=sorted(K.PREVIOUS.ACTIONS | {'mul','udiv','sdiv','urem','srem'})+['count']
    for xi,yi in [(0,1),(1,0),(2,3),(3,2)]:
        x,y=('var',xi),('var',yi);payload=('var',2 if xi<2 else 0)
        for direction in ['high','low']:
            op='countl_one' if direction=='high' else 'countr_one'
            for consumer in operations:
                family=f'{xi}_{yi}/{direction}/{consumer}'
                for form in range(4):
                    n=(op,y) if form%2==0 else (op.replace('one','zero'),('not',y))
                    e=n if consumer=='count' else (consumer,payload,n)
                    if form==0:g=('cmp0',x,('sub',y,K.ONE));truth=True
                    elif form==1:g=('cmp0',y,('add',x,K.ONE));truth=True
                    elif form==2:g=('cmp1',('sub',y,x),K.ONE);truth=False
                    else:
                        d=('sub',('add',y,('const',5)),('add',x,('const',5)))
                        g=('booland',('true',),('cmp0',d,K.ONE));truth=True
                    root=('select',g,e,K.Z) if truth else ('select',g,K.Z,e)
                    records.append(dict(id=f'{family}/{form}',family=family,form=form,
                                        pair=[xi,yi],root=root,path=[2 if truth else 3]))
    return records


def active_inputs(xi,yi,w):
    m=(1<<w)-1
    other=(2,3) if xi<2 else (0,1)
    for y in [0]+[1<<k for k in range(w)]:
        x=(y-1)&m
        for z,o in valid_masks(w):
            v=[0]*4;v[xi]=x;v[yi]=y;v[other[0]]=z;v[other[1]]=o
            yield v


def representations(out):
    started=time.perf_counter();scope=authority();rng=random.Random(20260913)
    data=dataset();save(out/'DATASET.json',data);records=[]
    for case in data:
        root=tree(case['root']);final,trace=certify(root,case['path'],scope,'context')
        xi,yi=case['pair'];checks=0
        for w in (2,3,4):
            for values in active_inputs(xi,yi,w):
                assert expr_value(root,values,w)==expr_value(final,values,w),(case['id'],w,values)
                checks+=1
        # Widths beyond enumeration, with legitimate masks and active premises.
        for w in (8,16,32,64,128,256):
            m=(1<<w)-1
            for _ in range(16):
                k=rng.randrange(w+1);y=0 if k==w else 1<<k;x=(y-1)&m
                z=rng.getrandbits(w);o=rng.getrandbits(w)&~z
                other=(2,3) if xi<2 else (0,1)
                values=[0]*4;values[xi]=x;values[yi]=y;values[other[0]]=z;values[other[1]]=o
                assert expr_value(root,values,w)==expr_value(final,values,w),(case['id'],w,values)
                checks+=1
        # The contract alone does not grant the binary observation.
        e=K.at(root,case['path'])
        naked_fail=False
        try:certify(e,[],scope,'context')
        except ValueError:naked_fail=True
        assert naked_fail,case['id']
        # Nor does this predecessor equality alone, for independent words.
        no_contract=False
        try:certify(root,case['path'],None,'guards')
        except ValueError:no_contract=True
        assert no_contract,case['id']
        records.append(dict(id=case['id'],family=case['family'],source_hash=digest(root),
                            final=final,trace=trace,finite_random_checks=checks,
                            missing_guard_refused=naked_fail,missing_contract_refused=no_contract))
    save(out/'results.json',dict(status='passed',cases=len(records),families=len({r['family'] for r in records}),
        finite_random_checks=sum(r['finite_random_checks'] for r in records),
        missing_premise_refusals=2*len(records),records=records,seconds=time.perf_counter()-started,
        scope='generated mechanism suite; finite/random checks supplement native all-width lemmas'))
    return dict(cases=len(records),checks=sum(r['finite_random_checks'] for r in records))


def development(out):
    scope=authority();records=[];rejections=[];checks=0
    x,y,z=('var',2),('var',3),('var',1);payload=('var',0)
    n=('countl_one',y);e=('lshr',payload,n)
    predecessor=('cmp0',y,('add',x,K.ONE))
    # Several genuine source premises, including a two-edge equality route,
    # explicit disjointness, and transport through positive coordinate equations.
    cases=[
        ('contract',predecessor,scope),
        ('explicit-disjoint',('booland',predecessor,('cmp0',('and',x,y),K.Z)),None),
        ('defined-predecessor',('cmp0',('and',y,('sub',y,K.ONE)),K.Z),None),
        ('two-edge',('booland',('cmp0',y,('add',z,K.ONE)),('cmp0',z,x)),scope),
        ('coordinate-transport',('booland',predecessor,('booland',('cmp0',x,z),('cmp0',('and',z,y),K.Z))),None),
    ]
    for name,g,auth in cases:
        root=('select',g,e,K.Z);final,trace=certify(root,[2],auth,'guards' if auth is None else 'context')
        count=0
        for w in (2,3):
            inputs=(a+b for a,b in itertools.product(valid_masks(w),repeat=2)) if auth is not None else itertools.product(range(1<<w),repeat=4)
            for values in inputs:
                assert expr_value(root,values,w)==expr_value(final,values,w),(name,w,values)
                count+=1
        records.append(dict(name=name,source=root,final=final,trace=trace,checks=count));checks+=count
    root=tree(records[0]['source']);final=tree(records[0]['final']);trace=records[0]['trace']
    def must_reject(name,root2,trace2,final2,scope2):
        try:K.replay(root2,trace2,final2,scope2)
        except (ValueError,KeyError,TypeError,IndexError) as ex:
            rejections.append(dict(name=name,reason=str(ex)));return
        raise AssertionError('accepted corruption: '+name)
    must_reject('absent-authority',root,trace,final,None)
    must_reject('different-source-authority',root,trace,final,dict(scope,entry='another_entry'))
    for name,mutate in [
        ('drop-route',lambda t:t[0]['parameter']['premises'].update(route=[])),
        ('wrong-predecessor',lambda t:t[0]['parameter']['premises'].update(predecessor=('var',0))),
        ('wrong-count',lambda t:t[0]['parameter'].update(count=('countl_zero',y))),
        ('swap-output-cells',lambda t:t[0]['proof']['supplied_cells'].reverse()),
        ('delete-coordinate-row',lambda t:t[0]['proof']['cover']['disjointness']['surviving_rows'].pop()),
        ('forge-protected-value',lambda t:t[0]['proof']['cover']['disjointness'].update(protected_values=[0,0])),
        ('forge-context',lambda t:t[0].update(guards=[])),
        ('forget-contract-policy',lambda t:t[0].update(policy='guards')),
        ('alter-output',lambda t:t[0].update(after=K.Z)),
        ('weaken-width',lambda t:t[0].update(minimum_width=1)),
    ]:
        t=copy.deepcopy(trace);mutate(t);must_reject(name,root,t,final,scope)
    # Rebind outer hashes as an adversary would; derivation still has to match
    # the actual path and word. Merely hashing is not the trust boundary.
    for name,r,p in [
        ('move-to-false-branch',('select',predecessor,K.Z,e),[3]),
        ('delete-source-guard',e,[]),
        ('unrelated-mask-pair',('select',('cmp0',y,('add',('var',0),K.ONE)),e,K.Z),[2]),
        ('false-conjunction',('select',('booland',predecessor,('cmp0',x,K.Z)),K.Z,e),[3]),
        ('true-disjunction',('select',('boolor',predecessor,('cmp0',x,K.Z)),e,K.Z),[2]),
    ]:
        t=copy.deepcopy(trace);t[0].update(path=p,before_hash=digest(r),guards=path_guards(r,p))
        f=replace(r,p,tree(t[0]['after']));t[0]['after_hash']=digest(f)
        must_reject(name,r,t,f,scope)
    # Explicit separating valuations for invalid unconditional extensions.
    sign=('select',('cmp2',y,K.Z),('lshr',payload,K.ONE),payload)
    negatives=[
        dict(name='guard-removed',width=2,values=[3,0,0,3],before=e,after=sign,valid_masks=True),
        dict(name='contract-removed',width=2,values=[3,0,2,3],before=e,after=sign,valid_masks=False),
        dict(name='wrong-count-kind',width=2,values=[3,0,1,2],before=('lshr',payload,('countl_zero',y)),after=sign,valid_masks=True),
        dict(name='wrong-mask-pair',width=2,values=[2,0,0,3],before=e,after=sign,valid_masks=True),
    ]
    for r in negatives:
        a=expr_value(r['before'],r['values'],r['width']);b=expr_value(r['after'],r['values'],r['width'])
        assert a!=b;r.update(before_value=a,after_value=b)
    # The real whole-source wrapper must reconstruct, rather than trust, scope.
    from context_stage_kernel import replay_prepared
    prepared=json.loads((ROOT/'development/uadd_v3/prepared/KnownBits_UaddSat.json').read_text())['partial_solution_10']
    bundle,_,_=load('KnownBits_UaddSat')
    for name,field,value in [('authority-entry','entry','partial_solution_11'),('authority-semantics','semantics','arbitrary-words')]:
        p=copy.deepcopy(prepared);p['context_authority'][field]=value
        try:replay_prepared(bundle,'partial_solution_10',p)
        except ValueError as ex:rejections.append(dict(name=name,reason=str(ex)))
        else:raise AssertionError(name)
    save(out/'development.json',dict(status='passed',checks=checks,cases=records,
        rejected_corruptions=rejections,separating_inputs=negatives))
    return dict(checks=checks,rejected_corruptions=len(rejections),separating_inputs=len(negatives))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--suite',choices=['development','representations'],required=True)
    p.add_argument('--output',type=lambda s:ROOT/s,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('use a new validation output directory')
    a.output.mkdir(parents=True)
    print(json.dumps(development(a.output) if a.suite=='development' else representations(a.output)))
