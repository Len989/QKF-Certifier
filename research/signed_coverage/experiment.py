"""Constructed guarded-coverage evidence; not a new holdout or a speed ranking.

Replay checks all saved proof cases and native records without discovery,
reference enumeration, or Java. Old-reference and failure outcomes remain
explicit diagnostics rather than mathematical proofs during replay.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time
from research.observations.model import Model, digest, require
from research.signed_bridge.model import request, word_value, CapacityExceeded
from research.signed_predicates import semantics as native
from research.signed_predicates.frontend import read_source
from research.unified.run import load_json, save_json
from research.unified import v6
from . import checker, runtime

FALSE = ['and', ['negative'], ['nonnegative']]
TRUE = ['or', ['negative'], ['nonnegative']]
POWER = ['and', ['positive'], ['popcount_eq', 1]]


def cases():
    rows = [(f'delayed_{k}',f'x == {1<<k}L',FALSE,'long','',k in (31,61)) for k in (4,8,30,31,40,61)]
    rows += [
        ('tautology_31','x == 2147483648L || x != 2147483648L',TRUE,'long','',True),
        ('contradiction_31','x == 2147483648L && x != 2147483648L',FALSE,'long','',False),
        ('odd_conflict_31','(x == 2147483648L) && ((x & 1) == 1)',FALSE,'long','',True),
        ('even_consequence_31','x != 2147483648L || (x & 1) == 0',TRUE,'long','',True),
        ('dead_31','x < 0',['negative'],'long','long dead=2147483648L;',False),
        ('carry_4','x + 1 == 16',FALSE,'long','',True),
        ('borrow_4','x - 1 == 16',FALSE,'long','',False),
        ('two_equalities','x == 16 || x == 32',FALSE,'long','',False),
        ('reverse_equality','16 == x',FALSE,'long','',False),
        ('negation_31','x != 2147483648L',TRUE,'long','',False),
        ('sign_disjunction_31','x == 2147483648L || x < 0',['negative'],'long','',True),
        ('sign_conjunction_31','x == 2147483648L && x > 0',FALSE,'long','',True),
        ('power_long','x > 0 && (x & (x-1)) == 0',POWER,'long','',True),
        ('power_int','x > 0 && (x & (x-1)) == 0',POWER,'int','',True),
        ('sign','x < 0',['negative'],'long','',False),
        ('nonzero','x != 0',['not',['popcount_eq',0]],'long','',False),
        ('small_width_only','x > 0 || (x == 2 && x < 0)',['positive'],'long','',True),
        ('masked_equality','(x & 31) == 16',FALSE,'long','',False)]
    for name,expr,goal,typ,prefix,use_java in rows:
        text=f'class Demo {{ public static boolean f({typ} x) {{ {prefix}return {expr}; }} }}'
        target={'schema':'qkf-target-v2','kind':'signed_boolean_predicate',
                'source':{'entry':{'class':'Demo','method':'f'},'word_type':typ},'goal':goal}
        yield name,text,target,use_java


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(output):
    manifest=load_json(output/'MANIFEST.json')
    actual={p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}-{'MANIFEST.json'}
    require(type(manifest) is dict and set(manifest)==actual,'exact experiment file set')
    for name,h in manifest.items(): require(sha(output/name)==h,'experiment hash: '+name)


def compare_full(old, new):
    pairs={(old.initial,new.initial)}; queue=list(pairs)
    for a,b in queue:
        require(old.terminal[a]==new.terminal[b],'full/covered source terminal disagreement')
        for bit in ('0','1'):
            pair=(old.step[a,bit][1],new.step[b,bit][1])
            if pair not in pairs:pairs.add(pair);queue.append(pair)
    return len(pairs)


def run(output, *, replay=False, java=False):
    output=Path(output)
    if replay:
        audit(output);original_summary=load_json(output/'SUMMARY.json')
        java=original_summary['java_executed_in_original_run']
    else: output.mkdir(parents=True,exist_ok=False)
    results,performance={},{}
    for name,text,target,use_java in cases():
        d=output/name;sel=request(target['source']['entry'],target['source']['word_type'])
        if replay:
            require((d/'source.java').read_text()==text and load_json(d/'target.json')==target,'fixed constructed inputs')
            proof=load_json(d/'proof.json')
        else:
            d.mkdir();(d/'source.java').write_text(text);save_json(d/'target.json',target)
            start=time.perf_counter();result,proof=v6.prove(text,target)
            require(proof is not None,'constructed target did not complete: '+name)
            performance[name]={'discovery_with_checks_seconds':time.perf_counter()-start}
            save_json(d/'proof.json',proof)
        start=time.perf_counter();result=v6.check(text,target,proof);info=v6.explain(text,target,proof)
        obs=proof['proof']['observations'];run_rows,receipt=runtime.load(text,sel,obs)
        original,_,model,metrics=checker.rebuild(text,sel,obs['source_model'])
        if not replay:performance[name]['separate_check_explain_load_seconds']=time.perf_counter()-start
        reference=None
        if not replay:
            from research.signed_bridge.producer import derive as old
            start=time.perf_counter()
            try:
                previous,out=old(text,sel)
                old_model=Model(previous['model'])
                reference={'status':'complete','full_states':len(old_model.states),
                           'checked_cross_product_states':compare_full(old_model,model)}
            except CapacityExceeded:
                reference={'status':'budget_exhausted','limit':64}
            performance[name]['separate_full_reference_seconds']=time.perf_counter()-start
            save_json(d/'reference.json',reference)
        else: reference=load_json(d/'reference.json')
        small,wide,java_count=0,0,0
        for w in range(1,9):
            for x in range(1<<w):
                require(native.evaluate(original,x,w)==word_value(model,x,w)==run_rows.value(x,w),
                        'whole-word/covered-model/row discrepancy')
                small+=1
        for w in (1,31,32,33,63,64,65,127,4096):
            for x in sorted({0,1,(1<<w)-1,1<<(w-1),2147483648 % (1<<w)}):
                require(native.evaluate(original,x,w)==word_value(model,x,w)==run_rows.value(x,w),
                        'wide source/covered/row discrepancy')
                wide+=1
        if java and use_java:
            width=32 if sel['word_type']=='int' else 64
            mask=(1<<width)-1
            xs=sorted(set(range(256))|{mask,1<<(width-1),(1<<(width-1))-1,2147483648&mask,(1<<61)&mask})
            if replay:
                record=load_json(d/'native.json')
                require(record['source_sha256']==original['source_sha256'] and record['width']==width
                        and record['inputs']==xs,'saved native population/binding')
                ys=record['outputs']
            else:
                from research.signed_predicates.frontend import select
                from research.signed_predicates.experiment import native as execute_java
                _,_,_,declaration,_=select(text,sel['entry'],word_type=sel['word_type'])
                start=time.perf_counter();ys=execute_java(declaration,'f',sel['word_type'],width,xs)
                performance[name]['native_seconds']=time.perf_counter()-start
                save_json(d/'native.json',{'source_sha256':original['source_sha256'],'width':width,'inputs':xs,'outputs':ys})
            require(type(ys) is list and len(ys)==len(xs) and all(type(y) is bool for y in ys),'native output types')
            for x,y in zip(xs,ys):require(y==native.evaluate(original,x,width)==run_rows.value(x,width),'actual Java/source/row')
            java_count=len(xs)
        if replay:
            require(result==load_json(d/'result.json') and info==load_json(d/'explain.json'),'replayed result/explanation')
        else:save_json(d/'result.json',result);save_json(d/'explain.json',info)
        results[name]={'status':result['status'],'coverage':metrics,'classes':receipt['classes'],
                       'product_states':result['inner']['target'].get('product_states'),
                       'witness_width':result['inner']['target'].get('witness_width'),
                       'proof_sha256':digest(proof),'proof_bytes':len(json.dumps(proof,sort_keys=True,separators=(',',':')).encode()),
                       'small_comparisons':small,'wide_comparisons':wide,'java_inputs':java_count,
                       'historical_reference_diagnostic':reference}
    if not replay:
        from .producer import infer
        controls={}
        sel=request({'class':'Demo','method':'f'},'long')
        for name,text,opts in (
            ('still_too_large','x == 4611686018427387904L',{}),
            ('state_budget','x == 16',{'max_states':1}),
            ('local_proof_budget','x==256 && x>0',{'max_local_steps':0}),
            ('reduction_budget','x==256 || x!=256',{'max_steps':0}),
            ('observation_budget','x==16',{'max_observations':0}),
            ('unsupported','x>>1 == 0',{})):
            source=f'class Demo {{ public static boolean f(long x) {{ return {text}; }} }}'
            start=time.perf_counter();cert,out=infer(source,sel,**opts)
            require(cert is None,'failure control must not produce proof')
            controls[name]=out;performance[name]={'failed_discovery_seconds':time.perf_counter()-start}
        text=next(s for n,s,t,j in cases() if n=='tautology_31')
        start=time.perf_counter();r,p=v6.prove(text,next(t for n,s,t,j in cases() if n=='tautology_31'),budgets={'max_target_states':1})
        require(p is None,'partial target is not proof');controls['target_budget']=r
        performance['target_budget']={'failed_discovery_seconds':time.perf_counter()-start}
        save_json(output/'CONTROLS.json',controls)
    summary={'schema':'qkf-guarded-coverage-development-v1','cases':results,
             'statuses':dict(sorted(Counter(r['status'] for r in results.values()).items())),
             'checked_proof_cases':len(results),'small_comparisons':sum(r['small_comparisons'] for r in results.values()),
             'wide_comparisons':sum(r['wide_comparisons'] for r in results.values()),
             'java_inputs':sum(r['java_inputs'] for r in results.values()),'mismatches':0,
             'java_executed_in_original_run':java,'new_holdout':False,
             'scope':'constructed coverage and target integration; not new external coverage or a speed ranking'}
    if replay:require(summary==original_summary,'reconstructed deterministic summary')
    else:
        save_json(output/'SUMMARY.json',summary);save_json(output/'PERFORMANCE.json',performance)
        save_json(output/'MANIFEST.json',{p.relative_to(output).as_posix():sha(p) for p in sorted(output.rglob('*')) if p.is_file()})
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path)
    p.add_argument('--replay',action='store_true');p.add_argument('--java',action='store_true');a=p.parse_args()
    print(json.dumps(run(a.output,replay=a.replay,java=a.java),sort_keys=True))
