"""Development-only representation study; original/native inputs are retained.

8 preceding context cases plus equality exponents 4,8,30,40. Packing still calls
legacy discovery/checking; compact replay does not generate pair lists. Costs
for packing, direct replay, DAG-only decoding, compatibility export and queried
separators are separate. No new external holdout or general speed claim.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time
from research.observations.model import require, digest
from research.signed_context.io import freeze, thaw, load_json, save_json
from research.signed_predicates.semantics import evaluate
from . import checker, dag, finite


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(root):
    manifest=load_json(root/'MANIFEST.json')
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}-{'MANIFEST.json'}
    require(set(manifest)==actual,'complete compact experiment manifest')
    for name,h in manifest.items():require(sha(root/name)==h,'compact manifest: '+name)


def run(root, *, input_root=None, replay=False):
    root=Path(root).resolve();performance={};details={}
    if replay:
        audit(root); expected=load_json(root/'SUMMARY.json'); names=sorted(expected['cases'])
    else:
        from research.signed_context.experiment import cases, audit as old_audit
        from research.unified.v7 import batch
        from .producer import pack_proofs
        input_root=Path(input_root).resolve();old_audit(input_root)
        root.mkdir(parents=True,exist_ok=False)
        names=[n for n,_,_ in cases()]+['delayed_4','delayed_8','delayed_30','delayed_40']
    for name in names:
        print('compact case: '+name,file=sys.stderr,flush=True)
        d=root/name
        if replay:
            source=(d/'source.java').read_text();targets=load_json(d/'targets.json');packet=load_json(d/'bundle.json')
        else:
            d.mkdir();old_dir=input_root/name
            start=time.perf_counter()
            if old_dir.is_dir():
                source=(old_dir/'source.java').read_text();targets=[load_json(old_dir/f'target-{i}.json') for i in range(4)]
                old=[load_json(old_dir/f'proof-{i}.json') for i in range(4)]
                native=load_json(old_dir/'native.json')
                save_json(d/'native.json',native)
            else:
                k=int(name.split('_')[1]);source=f'class Demo {{ public static boolean f(long x) {{ return x == {1<<k}L; }} }}'
                targets=next(ts for n,_,ts in cases() if n=='delayed_31')
                _,pairs=batch(source,targets);old=[p for _,p in pairs]
                require(all(p is not None for p in old),'complete equality control')
            prepare_seconds=time.perf_counter()-start
            start=time.perf_counter();results,packet=pack_proofs(source,targets,old);pack_seconds=time.perf_counter()-start
            (d/'source.java').write_text(source);save_json(d/'targets.json',targets);save_json(d/'bundle.json',packet)
            for i,p in enumerate(old):save_json(d/f'legacy-{i}.json',p)
            save_json(d/'results.json',results)
            # Single-target size is not conflated with the four-target sharing benefit.
            start=time.perf_counter();_,single=pack_proofs(source,targets[:1],old[:1]);single_seconds=time.perf_counter()-start
            save_json(d/'single.json',single)
            performance[name]={'prepare_legacy_seconds':prepare_seconds,'pack_and_builtin_check_seconds':pack_seconds,
                               'single_pack_and_check_seconds':single_seconds}
        # Full compact check is forbidden from materializing separators or invoking the old finite checker.
        expanded_calls=0;old_check_calls=0;source_calls=0
        def watch(frame,event,arg):
            nonlocal expanded_calls,old_check_calls,source_calls
            if event!='call':return
            mod=frame.f_globals.get('__name__');fun=frame.f_code.co_name
            if mod=='research.signed_compact.finite' and fun=='separator':expanded_calls+=1
            if mod=='research.observations.checker' and fun=='check':old_check_calls+=1
            if mod=='research.signed_predicates.frontend' and fun=='read_source':source_calls+=1
        prior=sys.getprofile();sys.setprofile(watch)
        try:ctx=checker.load(source,targets,packet)
        finally:sys.setprofile(prior)
        require((expanded_calls,old_check_calls,source_calls)==(0,0,1),'compact load call audit')
        results=ctx.results();require(results==load_json(d/'results.json'),'compact result replay')
        logical=dag.unpack(packet);obs=logical['source']['observations'];k=len(obs['blocks'])
        old=[load_json(d/f'legacy-{i}.json') for i in range(4)]
        require([r['status'] for r in results]==[p['result']['status'] for p in old],'verdict preserved')
        require([r['target'] for r in results]==[p['result']['inner']['target'] for p in old],'target obligations preserved')
        require(all(r['runtime']['action_sha256']==p['result']['inner']['runtime']['action_sha256'] for r,p in zip(results,old)),
                'labelled row action preserved')
        # Test all pairs externally; no all-pair list is stored in the compact proof or context.
        old_sep=old[0]['proof']['observations']['observations']['separators']
        for w in old_sep:require(ctx.explain_pair(w['left'],w['right'])['witness']==w,'pair explanation equivalence')
        query=ctx.explain_pair(max(0,k-2),k-1)
        if replay:require(query==load_json(d/'pair.json'),'requested pair replay')
        else:save_json(d/'pair.json',query)
        ir=thaw(ctx._ir_json);small=wide=native_count=0
        for width in range(1,9):
            for x in range(1<<width):
                require(ctx.value(x,width)==evaluate(ir,x,width),'small compact/source comparison');small+=1
        for width in (1,31,32,33,63,64,65,127,4096):
            for x in sorted({0,1,(1<<width)-1,1<<(width-1),2147483648%(1<<width)}):
                require(ctx.value(x,width)==evaluate(ir,x,width),'wide compact/source comparison');wide+=1
        if (d/'native.json').exists():
            native=load_json(d/'native.json')
            require(native['source_sha256']==ir['source_sha256'] and native['width']==(32 if logical['selection']['word_type']=='int' else 64),'native source binding')
            xs,ys=native['inputs'],native['outputs']
            require(type(xs) is list and type(ys) is list and len(xs)==len(ys) and all(type(y) is bool for y in ys),'native record types')
            for x,y in zip(xs,ys):require(ctx.value(x,native['width'])==evaluate(ir,x,native['width'])==y,'retained native/IR/compact')
            native_count=len(xs)
        if not replay:
            from research.unified.v6 import check as legacy_check
            start=time.perf_counter();exported=checker.export_legacy(source,targets,packet,0)
            require(legacy_check(source,targets[0],exported)==old[0]['result'],'unchanged old checker accepts export')
            require(exported==old[0],'canonical producer export roundtrip')
            performance[name]['explicit_export_and_old_check_seconds']=time.perf_counter()-start
            save_json(d/'export.json',exported)
            repetitions=[]
            for rep in range(3):
                row={}
                for route in (('legacy','compact') if rep%2==0 else ('compact','legacy')):
                    start=time.perf_counter()
                    if route=='legacy':
                        for t,p in zip(targets,old):legacy_check(source,t,p)
                    else:require(checker.check(source,targets,packet)==results,'timed compact replay')
                    row[route+'_seconds']=time.perf_counter()-start
                start=time.perf_counter();dag.unpack(packet);row['dag_decode_seconds']=time.perf_counter()-start
                start=time.perf_counter();ctx.explain_pair(max(0,k-2),k-1);row['one_warm_pair_seconds']=time.perf_counter()-start
                repetitions.append(row)
            performance[name]['repetitions']=repetitions
        single=load_json(d/'single.json')
        require(checker.check(source,targets[:1],single)==results[:1],'single proof independently replayed')
        details[name]={'source_sha256':ir['source_sha256'],'statuses':[r['status'] for r in results],
            'classes':k,'legacy_single_bytes':len(freeze(old[0]).encode()),'compact_single_bytes':len(freeze(single).encode()),
            'legacy_four_bytes':sum(len(freeze(p).encode()) for p in old),'compact_four_bytes':len(freeze(packet).encode()),
            'dag_nodes':len(packet['nodes']),'decoded_payload_bytes':len(freeze(logical).encode()),
            'stored_separators':0,'tested_pairs':len(old_sep),'max_tested_context':max((len(w['word']) for w in old_sep),default=0),
            'load_audit':{'source_parses':source_calls,'old_finite_checks':old_check_calls,'pair_materializations':expanded_calls},
            'small_comparisons':small,'wide_comparisons':wide,'retained_native_comparisons':native_count,
            'packet_sha256':digest(packet)}
    summary={'schema':'qkf-compact-development-v1','cases':details,'sources':len(details),
        'target_proofs':sum(len(d['statuses']) for d in details.values()),
        'statuses':dict(sorted(Counter(s for d in details.values() for s in d['statuses']).items())),
        'small_comparisons':sum(d['small_comparisons'] for d in details.values()),
        'wide_comparisons':sum(d['wide_comparisons'] for d in details.values()),
        'retained_native_comparisons':sum(d['retained_native_comparisons'] for d in details.values()),
        'tested_pairs':sum(d['tested_pairs'] for d in details.values()),'mismatches':0,
        'java_executed_by_compact_experiment':False,'new_holdout':False,
        'scope':'compact storage and source-bound replay; legacy discovery and its allocations remain'}
    if replay:require(summary==expected,'compact summary replay')
    else:
        save_json(root/'SUMMARY.json',summary);save_json(root/'PERFORMANCE.json',{'python':sys.version,'cases':performance})
        save_json(root/'MANIFEST.json',{p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file()})
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output');p.add_argument('--input');p.add_argument('--replay',action='store_true')
    a=p.parse_args();print(json.dumps(run(a.output,input_root=a.input,replay=a.replay),sort_keys=True))
