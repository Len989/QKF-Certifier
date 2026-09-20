"""Eight constructed source contexts, four independent target requests each.

Records the complete source discovery, checked load, additional target work,
three paired old/session replays and cold-process checks separately. This is
not a new holdout, source-semantic change or general speed ranking. Replay
checks stored proofs/native outputs, not discovery/measurement diagnostics.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

from research.observations.model import digest, require
from research.signed_bridge.model import request
from research.signed_predicates import semantics as native
from . import session
from .io import load_json, save_json, freeze

TRUE=['or',['negative'],['nonnegative']]
FALSE=['and',['negative'],['nonnegative']]
POWER=['and',['positive'],['popcount_eq',1]]
ROOT=Path(__file__).resolve().parents[2]


def cases():
    rows=[('power_long','x > 0 && (x & (x-1)) == 0',POWER,'long'),
          ('power_int','x > 0 && (x & (x-1)) == 0',POWER,'int'),
          ('sign','x < 0',['negative'],'long'),
          ('tautology_31','x == 2147483648L || x != 2147483648L',TRUE,'long'),
          ('odd_conflict_31','(x == 2147483648L) && ((x & 1) == 1)',FALSE,'long'),
          ('delayed_31','x == 2147483648L',FALSE,'long'),
          ('delayed_61','x == 2305843009213693952L',FALSE,'long'),
          ('small_width_only','x > 0 || (x == 2 && x < 0)',['positive'],'long')]
    for name,expr,base,typ in rows:
        text=f'class Demo {{ public static boolean f({typ} x) {{ return {expr}; }} }}'
        goals=[base,['not',base],TRUE,FALSE]
        targets=[{'schema':'qkf-target-v2','kind':'signed_boolean_predicate',
                  'source':{'entry':{'class':'Demo','method':'f'},'word_type':typ},'goal':g} for g in goals]
        yield name,text,targets


TRACKED={('research.signed_predicates.frontend','read_source'):'source_parses',
         ('research.signed_coverage.checker','rebuild_observations'):'shared_rebuilds',
         ('research.observations.checker','check'):'atomic_checks'}


def reuse_audit(text,sel,obs,targets,proofs,results):
    """Separate untimed call audit; no profiler overhead in phase measurements."""
    counts={name:0 for name in TRACKED.values()}
    def record(frame,event,arg):
        if event=='call':
            key=(frame.f_globals.get('__name__'),frame.f_code.co_name)
            if key in TRACKED:counts[TRACKED[key]]+=1
    previous=sys.getprofile();sys.setprofile(record)
    try:
        ctx=session.load(text,sel,obs);after_load=dict(counts)
        for target,proof,result in zip(targets,proofs,results):
            require(ctx.check(target,proof)==result,'warm target check')
            require(ctx.explain(target,proof)['result']==result,'warm explanation')
        after_all=dict(counts)
    finally:sys.setprofile(previous)
    require(after_load=={'source_parses':1,'shared_rebuilds':1,'atomic_checks':1},'one complete shared check')
    require(after_all==after_load,'additional target work reconstructed the source')
    return {'after_load':after_load,'after_four_checks_and_explanations':after_all}


def cold_checks(directory):
    import subprocess
    script='''import importlib,json,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1]);p=Path(sys.argv[2])
module=importlib.import_module('research.unified.'+sys.argv[3])
source=(p/'source.java').read_text();target=json.loads((p/'target-0.json').read_text());proof=json.loads((p/'proof-0.json').read_text())
start=time.perf_counter();result=module.check(source,target,proof);elapsed=time.perf_counter()-start
from research.observations.model import digest
print(json.dumps({'result_sha256':digest(result),'api_seconds':elapsed,'research_modules':sorted(n for n in sys.modules if n.startswith('research.'))},sort_keys=True))
'''
    records=[]
    for repeat in range(3):
        for route in (('v6','v7') if repeat%2==0 else ('v7','v6')):
            start=time.perf_counter()
            process=subprocess.run([sys.executable,'-I','-B','-c',script,str(ROOT),str(directory),route],
                                   capture_output=True,text=True,timeout=120)
            elapsed=time.perf_counter()-start
            require(process.returncode==0,'cold check failed: '+process.stderr)
            record=json.loads(process.stdout)
            require(record['result_sha256']==digest(load_json(directory/'result-0.json')),'cold check result')
            if route=='v7':
                require(not any(n.startswith(('research.graal','research.knownbits','research.inference'))
                                or n=='research.observations.run_package' for n in record['research_modules']),
                        'unrelated legacy profile imported by v7')
            records.append({'route':route,'repeat':repeat,'process_wall_seconds':elapsed,**record})
    return records


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(output):
    manifest=load_json(output/'MANIFEST.json')
    actual={p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}-{'MANIFEST.json'}
    require(type(manifest) is dict and set(manifest)==actual,'complete experiment manifest')
    for name,h in manifest.items():require(sha(output/name)==h,'experiment hash: '+name)


def run(output,*,replay=False,java=False,cold=True):
    output=Path(output).resolve()
    if replay:
        audit(output);expected=load_json(output/'SUMMARY.json')
        java=expected['java_executed_in_original_run']
    else:output.mkdir(parents=True,exist_ok=False)
    details,performance={},{}
    for name,text,targets in cases():
        print("context case: " + name, file=sys.stderr, flush=True)
        d=output/name;sel=request(targets[0]['source']['entry'],targets[0]['source']['word_type'])
        if replay:
            require((d/'source.java').read_text()==text,'fixed constructed source')
            obs=load_json(d/'observations.json')
            ctx=session.load(text,sel,obs)
        else:
            from research.unified import v6
            d.mkdir();(d/'source.java').write_text(text)
            start=time.perf_counter();ctx,_=session.build(text,sel)
            require(ctx is not None,'constructed source context exhausted')
            performance[name]={'source_discovery_and_load_seconds':time.perf_counter()-start}
            obs=ctx.export_source_proof();save_json(d/'observations.json',obs)
            start=time.perf_counter();pairs=ctx.prove_many(targets)
            performance[name]['four_targets_discovery_and_checks_seconds']=time.perf_counter()-start
        results,proofs=[],[]
        for i,target in enumerate(targets):
            if replay:
                require(load_json(d/f'target-{i}.json')==target,'independent target binding')
                proof=load_json(d/f'proof-{i}.json');result=ctx.check(target,proof)
            else:
                result,proof=pairs[i];require(proof is not None,'main target exhausted')
                save_json(d/f'target-{i}.json',target);save_json(d/f'proof-{i}.json',proof)
                require(v6.check(text,target,proof)==result,'unchanged v6 checker disagrees')
            explanation=ctx.explain(target,proof)
            if replay:
                require(result==load_json(d/f'result-{i}.json'),'context result mismatch')
                require(explanation==load_json(d/f'explain-{i}.json'),'context explanation mismatch')
            else:
                save_json(d/f'result-{i}.json',result);save_json(d/f'explain-{i}.json',explanation)
            proofs.append(proof);results.append(result)
        calls=reuse_audit(text,sel,obs,targets,proofs,results)
        ir=json.loads(ctx._ir_json)  # Checked immutable IR, only for explicit finite controls.
        small=0
        for width in range(1,9):
            for raw in range(1<<width):
                require(ctx.value(raw,width)==native.evaluate(ir,raw,width),'context/source point comparison')
                small+=1
        wide=0
        for width in (1,31,32,33,63,64,65,127,4096):
            for raw in sorted({0,1,(1<<width)-1,1<<(width-1),2147483648%(1<<width)}):
                require(ctx.value(raw,width)==native.evaluate(ir,raw,width),'wide source/context')
                wide+=1
        native_count=0
        if java:
            width=32 if sel['word_type']=='int' else 64;mask=(1<<width)-1
            xs=sorted(set(range(256))|{mask,1<<(width-1),(1<<(width-1))-1,2147483648&mask,(1<<61)&mask})
            if replay:
                record=load_json(d/'native.json')
                require(record['source_sha256']==ir['source_sha256'] and record['width']==width
                        and record['inputs']==xs,'saved native binding/population')
                ys=record['outputs']
            else:
                from research.signed_predicates.frontend import select
                from research.signed_predicates.experiment import native as execute_java
                _,_,_,declaration,_=select(text,sel['entry'],word_type=sel['word_type'])
                start=time.perf_counter();ys=execute_java(declaration,'f',sel['word_type'],width,xs)
                performance[name]['java_seconds']=time.perf_counter()-start
                save_json(d/'native.json',{'source_sha256':ir['source_sha256'],'width':width,'inputs':xs,'outputs':ys})
            require(type(ys) is list and len(ys)==len(xs) and all(type(y) is bool for y in ys),'native output types')
            for raw,y in zip(xs,ys):require(y==native.evaluate(ir,raw,width)==ctx.value(raw,width),'native/context/IR')
            native_count=len(xs)
        if not replay:
            repetitions=[]
            for repeat in range(3):
                row={}
                for route in (('old','session') if repeat%2==0 else ('session','old')):
                    start=time.perf_counter()
                    if route=='session':
                        loaded=session.load(text,sel,obs);load_end=time.perf_counter()
                        for t,p,r in zip(targets,proofs,results):require(loaded.check(t,p)==r,'session timing result')
                        end=time.perf_counter()
                        row.update({'checked_load_seconds':load_end-start,
                                    'four_additional_checks_seconds':end-load_end,'session_total_seconds':end-start})
                    else:
                        for t,p,r in zip(targets,proofs,results):require(v6.check(text,t,p)==r,'old timing result')
                        row['four_old_checks_seconds']=time.perf_counter()-start
                repetitions.append(row)
            performance[name]['paired_replay_repetitions']=repetitions
            performance[name]['cold_checks']=cold_checks(d) if cold else []
        details[name]={'source_sha256':ir['source_sha256'],'classes':ctx.describe()['runtime']['classes'],
                       'statuses':[r['status'] for r in results],'proof_sha256':[digest(p) for p in proofs],
                       'proof_bytes':[len(freeze(p).encode()) for p in proofs],
                       'shared_call_audit':calls,'small_comparisons':small,'wide_comparisons':wide,
                       'java_inputs':native_count}
    if not replay:
        controls={}
        sel=request({'class':'Demo','method':'f'},'long')
        for name,expr,options in [('state_budget','x<0',{'max_states':1}),
                                  ('unsupported','x>>1==0',{}),('too_large','x==4611686018427387904L',{})]:
            text=f'class Demo {{ public static boolean f(long x) {{ return {expr}; }} }}'
            start=time.perf_counter();ctx,outcome=session.build(text,sel,limits=options)
            require(ctx is None,'failure control must not create context');controls[name]=outcome
            performance[name]={'failed_source_discovery_seconds':time.perf_counter()-start}
        text=next(t for n,t,ts in cases() if n=='power_long');ctx,_=session.build(text,sel)
        t=next(ts[0] for n,t,ts in cases() if n=='power_long')
        start=time.perf_counter();r,p=ctx.prove(t,limits={'max_target_states':1})
        require(p is None,'incomplete product cannot be proof');controls['target_budget']=r
        performance['target_budget']={'failed_target_discovery_seconds':time.perf_counter()-start}
        save_json(output/'CONTROLS.json',controls)
    summary={'schema':'qkf-context-development-v1','cases':details,'contexts':len(details),
             'target_proofs':sum(len(r['statuses']) for r in details.values()),
             'statuses':dict(sorted(Counter(s for r in details.values() for s in r['statuses']).items())),
             'small_comparisons':sum(r['small_comparisons'] for r in details.values()),
             'wide_comparisons':sum(r['wide_comparisons'] for r in details.values()),
             'java_inputs':sum(r['java_inputs'] for r in details.values()),'mismatches':0,
             'java_executed_in_original_run':java,'new_holdout':False,
             'scope':'same PR35 sources/semantics; reuse and exact old proof compatibility, not new family coverage'}
    if replay:require(summary==expected,'reconstructed context summary')
    else:
        save_json(output/'SUMMARY.json',summary)
        save_json(output/'PERFORMANCE.json',{'python':sys.version,'platform':platform.platform(),'cases':performance})
        save_json(output/'MANIFEST.json',{p.relative_to(output).as_posix():sha(p) for p in sorted(output.rglob('*')) if p.is_file()})
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path)
    p.add_argument('--replay',action='store_true');p.add_argument('--java',action='store_true');p.add_argument('--no-cold',action='store_true')
    args=p.parse_args()
    print(json.dumps(run(args.output,replay=args.replay,java=args.java,cold=not args.no_cold),sort_keys=True))
