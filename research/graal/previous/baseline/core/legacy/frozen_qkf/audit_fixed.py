#!/usr/bin/env python3
"""Frozen-rule generalization audit. Structural coverage is not correctness."""
from pathlib import Path
import argparse,collections,hashlib,json,pickle,subprocess,sys,time
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'dependencies'))


def validate_freeze(repo):
    frozen=json.loads((ROOT/'FROZEN_CONFIGURATION.json').read_text())
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()!=frozen['qkf_commit']:
        raise ValueError('QKF commit mismatch')
    for name,digest in frozen['unchanged_dependencies'].items():
        if hashlib.sha256((ROOT/'dependencies'/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('frozen dependency changed: '+name)
    return frozen


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--repo',type=Path,required=True)
    ap.add_argument('--corpus',type=Path,required=True);ap.add_argument('--helpers',type=Path,required=True)
    ap.add_argument('--out',type=Path,default=ROOT/'results');args=ap.parse_args()
    repo=args.repo.resolve();frozen=validate_freeze(repo);args.out.mkdir(parents=True,exist_ok=True)
    sys.path[:0]=[str(repo/'src'),str(repo/'tests')]
    from qkf_certifier.frontend import parse_bundle,expression
    from qkf_certifier.producer import normalize
    from qkf_certifier.kernel import replay as public_replay,digest,hashes,CONTRACT,children
    from qkf_certifier.certificate import SCHEMA
    from guard_kernel import produce,replay
    from regular_interfaces import supported,order,target_for,PLAIN,COMPS,MINMAX
    start=time.perf_counter();records=[];cache=[];rule_counts=collections.Counter()
    for path in sorted(args.corpus.glob('*/solution.mlir')):
        source=path.read_text();bundle={'program':source}
        if 'func.call @meet(' in source:bundle['meet']=(args.helpers/'meet.mlir').read_text()
        if 'func.call @getTop(' in source:bundle['top']=(args.helpers/'top.mlir').read_text()
        fs=parse_bundle(bundle)
        for entry in fs:
            if not(entry=='solution' or entry.endswith('_body') or (entry.startswith('partial_solution_') and not entry.endswith('_cond'))):continue
            role='solution' if entry=='solution' else 'body' if entry.endswith('_body') else 'component'
            target,scope=target_for(path.parent.name)
            r={'operator':path.parent.name,'entry':entry,'role':role,'target':target,'target_scope':scope}
            try:
                initial=expression(fs,entry);nf,steps=normalize(initial)
                cert={'schema':SCHEMA,'sources':hashes(bundle),'entry':entry,'semantics':CONTRACT,
                      'initial_hash':digest(initial),'steps':steps,'normal_form':nf,'target':None}
                cert=json.loads(json.dumps(cert));assert public_replay(bundle,entry,cert)==nf
                simple,trace=produce(nf,2);assert replay(nf,trace,simple,2)==simple
                ns=order(simple)
                def unsupported(n):
                    return n[0] not in PLAIN|COMPS|MINMAX and not(n[0] in ('shl','lshr','ashr') and n[2]==('const',1))
                blockers=collections.Counter(n[0] for n in ns if unsupported(n))
                r.update({'status':'rewritten_and_replayed','regular_before':supported(nf),'regular_after':supported(simple),
                          'nodes_before':len(order(nf)),'nodes_after':len(ns),'additional_rewrites':len(trace),
                          'rules':dict(collections.Counter(s['rule'] for s in trace)),'blockers':dict(blockers)})
                rule_counts.update(s['rule'] for s in trace)
                cache.append({'record':r,'bundle':bundle,'nf':nf,'normalization':cert,'simple':simple,'rewrites':trace})
            except Exception as ex:
                r.update({'status':'failed','reason':type(ex).__name__+': '+str(ex)})
            records.append(r)
        print(path.parent.name,'audited',flush=True)
    summary={}
    for role in ('solution','body','component'):
        rs=[r for r in records if r['role']==role];ok=[r for r in rs if r['status']=='rewritten_and_replayed']
        summary[role]={'total':len(rs),'replayed':len(ok),'regular_before':sum(r['regular_before'] for r in ok),
                       'regular_after':sum(r['regular_after'] for r in ok),
                       'regular_and_target_supported':sum(r['regular_after'] and r['target'] is not None for r in ok)}
    result={'configuration':frozen,'semantics':CONTRACT,'summary':summary,'rules_used':dict(rule_counts),
            'records':records,'elapsed_seconds':time.perf_counter()-start,
            'scope':'Uniform application of byte-identical Smax rules. Syntax coverage is separate from target correctness.'}
    (args.out/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    with (args.out/'local_cache.pkl').open('wb') as f:pickle.dump(cache,f)
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':main()
