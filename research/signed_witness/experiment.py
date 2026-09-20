"""Constructed PR34 study: full discovery, old control and replay are distinct.

Replay rechecks every saved proof against its actual source/goal. No-witness and
failed discovery reports remain diagnostic data, not proof certificates. Optional
fresh Java is finite validation at the selected native width, never width lifting.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time
from research.observations.model import integer, require
from research.signed_predicates.frontend import select
from research.unified.run import load_json, save_json
from research.unified.v5 import check, explain
from .common import ENGINE, point, prepare

ROOT = Path(__file__).resolve().parents[2]
FALSE = ['and', ['negative'], ['nonnegative']]
TRUE = ['or', ['negative'], ['nonnegative']]
POWER = ['and', ['positive'], ['popcount_eq', 1]]


def sha(raw): return hashlib.sha256(raw).hexdigest()


def cases():
    for name, expression, goal, typ, expected in (
        ('delayed_31','x == 2147483648L',FALSE,'long','refuted'),
        ('delayed_62','x == 4611686018427387904L',FALSE,'long','refuted'),
        ('no_zero_guard','(x & (x-1))==0',POWER,'long','refuted'),
        ('no_sign_guard','x!=0 && (x & (x-1))==0',POWER,'long','refuted'),
        ('wrong_connective','x>0 || (x & (x-1))==0',POWER,'long','refuted'),
        ('small_width_only','x>0 || (x==2 && x<0)',['positive'],'long','refuted'),
        ('later_failure','x==256 && x>0',FALSE,'long','refuted'),
        ('power_int','x>0 && (x & (x-1))==0',POWER,'int','certified'),
        ('power_long','x>0 && (x & (x-1))==0',POWER,'long','certified'),
        ('negative','x<0',['negative'],'long','certified'),
        ('constant','true',TRUE,'long','certified'),
        ('tautology_31','x == 2147483648L || x != 2147483648L',TRUE,'long','budget_exhausted'),
    ):
        text = f'class Demo {{ public static boolean f({typ} x) {{ return {expression}; }} }}'
        target = {'schema':'qkf-target-v2','kind':'signed_boolean_predicate',
                  'source':{'entry':{'class':'Demo','method':'f'},'word_type':typ},'goal':goal}
        yield name, text, target, expected, None
    for typ,width in (('int',32),('long',64)):
        text=f'class Demo {{ public static boolean f({typ} x) {{ return x!=0 && (x & (x-1))==0; }} }}'
        target={'schema':'qkf-target-v2','kind':'signed_boolean_predicate',
                'source':{'entry':{'class':'Demo','method':'f'},'word_type':typ},'goal':POWER}
        yield 'native_'+typ,text,target,'refuted',(1<<(width-1),width)


def run(output, *, replay=False, java=False):
    output=Path(output)
    require(not (replay and java), 'replay cannot execute Java')
    if replay:
        manifest=load_json(output/'MANIFEST.json')
        require(set(manifest)=={p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}-{'MANIFEST.json'},'exact file set')
        for name,expected in manifest.items(): require(sha((output/name).read_bytes())==expected,'artifact: '+name)
        java=load_json(output/'SUMMARY.json')['java_executed_in_original_run']
    else:
        require(not output.exists(),'new output directory');output.mkdir(parents=True)
    results,costs={},{}
    for name,text,goal,expected,supplied in cases():
        d=output/name
        if replay:
            require((d/'source.java').read_text()==text and load_json(d/'target.json')==goal,'source/target identity')
            saved=load_json(d/'result.json');diag=load_json(d/'discovery.json')
            proof=load_json(d/'proof.json') if (d/'proof.json').exists() else None
        else:
            from research.unified.v5 import prove_with_diagnostics, witness
            d.mkdir();(d/'source.java').write_text(text,encoding='utf-8');save_json(d/'target.json',goal)
            start=time.perf_counter()
            if supplied is None:
                saved,proof,diag=prove_with_diagnostics(text,goal)
            else:
                saved,proof=witness(text,goal,*supplied)
                diag={'precheck':{'outcome':'supplied_word','evaluations':0,'is_certificate':False},
                      'fallback_used':False,'is_certificate':False}
            costs[name]={'full_discovery_and_builtin_checks_seconds':time.perf_counter()-start}
            save_json(d/'result.json',saved);save_json(d/'discovery.json',diag)
            if proof is not None:save_json(d/'proof.json',proof)
            # Old route is a separately timed control, not a required stage of the new path.
            from research.unified.v4 import prove as old_prove
            start=time.perf_counter();old_result,old_proof=old_prove(text,goal)
            costs[name]['separate_v4_control_seconds']=time.perf_counter()-start
            save_json(d/'v4_control.json',{'result':old_result,'proof_bytes':None if old_proof is None
                                         else len(json.dumps(old_proof,sort_keys=True,separators=(',',':')).encode())})
        require(saved['status']==expected,'case result: '+name)
        if proof is not None:
            start=time.perf_counter();result=check(text,goal,proof);explanation=explain(text,goal,proof)
            require(result==saved,'fresh proof replay: '+name)
            if replay:require(load_json(d/'explanation.json')==explanation,'explanation replay')
            else:
                costs[name]['separate_check_and_explain_seconds']=time.perf_counter()-start
                save_json(d/'explanation.json',explanation)
        else:
            require(expected=='budget_exhausted','only declared failure can omit a proof');result=saved
        compiled,ir=prepare(text,goal)
        small_count=0
        if proof is not None and result['engine']==ENGINE:
            w=result['inner']['witness_width'];x=result['inner']['input']
            actual,target_value=point(compiled,ir,x,w)
            require(actual!=target_value,'concrete witness re-evaluation')
        # Separate reference comparisons with the raw signed contract, not another carrier.
        from research.signed_predicates.semantics import evaluate
        from research.signed_predicates.frontend import target_value
        native_width=32 if goal['source']['word_type']=='int' else 64
        for width in range(1,7):
            for x in range(1<<width):
                actual,e=point(compiled,ir,x,width)
                require(actual==evaluate(ir,x,width) and e==target_value(goal['goal'],bin(x).count('1'),x>>(width-1)),
                        'point source/target semantics')
                small_count+=1
        native_count=native_mismatches=0
        if java:
            xs=sorted(set(range(256)) | {1<<(native_width-1),(1<<(native_width-1))-1,(1<<native_width)-1}
                      | ({1<<31,1<<62,256} if native_width==64 else {256}))
            harness=sha((ROOT/'research/signed_predicates/experiment.py').read_bytes())
            if replay:native=load_json(d/'native.json')
            else:
                from research.signed_predicates.experiment import native as run_java
                declaration=select(text,goal['source']['entry'],word_type=goal['source']['word_type'])[3]
                start=time.perf_counter();ys=run_java(declaration,'f',goal['source']['word_type'],native_width,xs)
                costs[name]['java_seconds']=time.perf_counter()-start
                native={'width':native_width,'inputs':xs,'outputs':ys,'source_sha256':ir['source_sha256'],
                        'declaration_sha256':ir['declaration_sha256'],'harness_sha256':harness}
                save_json(d/'native.json',native)
            require(native['inputs']==xs and native['width']==native_width
                    and native['source_sha256']==ir['source_sha256'] and native['declaration_sha256']==ir['declaration_sha256']
                    and native['harness_sha256']==harness and type(native['outputs']) is list
                    and len(native['outputs'])==len(xs) and all(type(y) is bool for y in native['outputs']), 'native record identity')
            for x,y in zip(xs,native['outputs']):
                a,e=point(compiled,ir,x,native_width);require(a==y,'actual Java/IR correspondence');native_mismatches+=y!=e
            native_count=len(xs)
            if expected=='certified' or name in {'small_width_only','tautology_31'}:require(native_mismatches==0,'native positive/control')
            else:require(native_mismatches>0,'native negative control must exhibit mismatch')
            if supplied is not None:
                require(supplied[0] in xs and native['outputs'][xs.index(supplied[0])]==result['inner']['output'],'supplied native witness executed')
        old=load_json(d/'v4_control.json')
        results[name]={'status':result['status'],'engine':result['engine'],'has_proof':proof is not None,
                       'precheck_outcome':diag['precheck']['outcome'], 'evaluations':diag['precheck']['evaluations'],
                       'fallback_used':diag['fallback_used'],'v4_status':old['result']['status'],
                       'witness_width':(result['inner'].get('witness_width') if result['engine']==ENGINE
                                        else result.get('inner',{}).get('target',{}).get('witness_width')),
                       'proof_sha256':None if proof is None else sha((d/'proof.json').read_bytes()),
                       'small_point_checks':small_count,'java_inputs':native_count,'java_target_mismatches':native_mismatches}
    if not replay:
        from research.unified.v5 import prove_with_diagnostics
        controls={}
        text='class Demo { public static boolean f(long x) { return x>0; } }'
        goal={'schema':'qkf-target-v2','kind':'signed_boolean_predicate',
              'source':{'entry':{'class':'Demo','method':'f'},'word_type':'long'},'goal':['positive']}
        for name,s,options in (
            ('unsupported',text.replace('x>0','(x >> 1)>0'),None),
            ('both_budgets',text,{'search':{'max_evaluations':0},'fallback':{'max_states':1}}),
            ('disabled_search',text,{'search':{'max_width':0}}),
        ):
            start=time.perf_counter();r,p,diag=prove_with_diagnostics(s,goal,budgets=options)
            costs[name]={'control_discovery_seconds':time.perf_counter()-start}
            require(r['status']==('unsupported' if name=='unsupported' else 'certified' if name=='disabled_search' else 'budget_exhausted'), 'control result')
            controls[name]={'source':s,'target':goal,'options':options,'result':r,'diagnostics':diag,'proof':p}
        save_json(output/'CONTROLS.json',controls)
    controls=load_json(output/'CONTROLS.json')
    for c in controls.values():
        if c['proof'] is not None:require(check(c['source'],c['target'],c['proof'])==c['result'],'control proof replay')
    summary={'schema':'qkf-concrete-witness-development-v1','cases':results,
             'status_counts':dict(sorted(Counter(r['status'] for r in results.values()).items())),
             'engine_counts':dict(sorted(Counter(r['engine'] for r in results.values()).items())),
             'proof_cases':sum(r['has_proof'] for r in results.values()),
             'control_proofs':sum(c['proof'] is not None for c in controls.values()),
             'small_point_checks':sum(r['small_point_checks'] for r in results.values()),
             'java_inputs':sum(r['java_inputs'] for r in results.values()),'java_source_mismatches':0,
             'java_executed_in_original_run':java,'new_holdout':False,
             'replay_scope':'recheck all actual proofs and saved native outputs; search/failure/v4-control records remain diagnostics'}
    if replay:require(load_json(output/'SUMMARY.json')==summary,'summary replay')
    else:
        save_json(output/'SUMMARY.json',summary);save_json(output/'PERFORMANCE.json',costs)
        save_json(output/'MANIFEST.json',{p.relative_to(output).as_posix():sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()})
    return summary


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path)
    p.add_argument('--replay',action='store_true');p.add_argument('--java',action='store_true');a=p.parse_args(argv)
    print(json.dumps(run(a.output,replay=a.replay,java=a.java),sort_keys=True))


if __name__=='__main__':main()
