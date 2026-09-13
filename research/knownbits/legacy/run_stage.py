"""Run identical LLVM inputs with the bounded-mask and case-composition kernel."""
from pathlib import Path
import argparse,collections,json,resource,signal,subprocess,sys,time,traceback
from common import ROOT,BASE,setup,check_baseline,save
class Timeout(Exception):pass
def alarm(signum,frame):raise Timeout()

def case(op,repo,mode):
    from regular_interfaces import tree
    from qkf_certifier.kernel import digest,hashes,CONTRACT
    from qkf_certifier.frontend import parse_bundle
    from observer_kernel import EXTENSION as OLD
    from mask_observers import produce as masks,replay as replay_masks,EXTENSION as MASK
    from branch_kernel import EXTENSION as COMPOSITION
    from branch_producer import produce,ProofFailure
    from certificates import SCHEMA,verify
    from prefix_masks import BACKEND,shape
    from prove_umin import one_bit
    from word_oracle import evaluate
    budgets=json.loads((ROOT/'STAGE.json').read_text())['budgets'];out=ROOT/'results'/mode
    bundle={'program':(BASE/'cases'/(op+'.mlir')).read_text()}
    data=json.loads((BASE/'results/expressions'/(op+'.json')).read_text());old=tree(data['observed'])
    r={'case':op,'mode':mode,'status':'started'};start=time.perf_counter();phase='mask_normalization'
    signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,budgets['producer_seconds_per_case'])
    try:
        e,tr=masks(old,2);r.update(mask_rewrites=len(tr),mask_rules=dict(collections.Counter(x['rule'] for x in tr)),shape=shape(e,op))
        save(out/'expressions'/(op+'.json'),{'observed':e,'mask_trace':tr})
        rows,bad=one_bit(parse_bundle(bundle),'solution',op,evaluate)
        if bad:raise ProofFailure({'status':'counterexample_width_one','witness':bad})
        phase='proof_search'
        def progress(totals,leaf):
            r['progress']=dict(totals);r['last_leaf']={k:v for k,v in leaf.items() if k!='path'}
            save(out/'progress'/(op+'.json'),r)
        proof,totals,leaves=produce(e,op,budgets,progress,split=mode=='composed')
        cert={'schema':SCHEMA,'backend':BACKEND,'legacy_extension':OLD,'mask_extension':MASK,'composition_extension':COMPOSITION,
              'target':op,'entry':'solution','semantics':CONTRACT,'sources':hashes(bundle),'min_rewrite_width':2,
              'normalization':data['normalization'],'simplified':data['simplified'],'guard_trace':data['guard_trace'],
              'old_observed':old,'observer_trace':data['observer_trace'],'observed':e,'mask_trace':tr,'observed_hash':digest(e),
              'width_one':rows,'proof':proof}
        cert=json.loads(json.dumps(cert));p=out/'certificates'/(op+'.json');p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(cert,separators=(',',':'))+'\n')
        r.update(status='produced',producer_seconds=time.perf_counter()-start,certificate_bytes=p.stat().st_size,certificate=str(p.relative_to(ROOT)),**totals)
        save(out/'leaves'/(op+'.json'),leaves)
        signal.setitimer(signal.ITIMER_REAL,0);phase='replay';t=time.perf_counter();signal.setitimer(signal.ITIMER_REAL,budgets['replay_seconds_per_case'])
        checks=verify(bundle,cert,op);r.update(status='proved_sound_all_positive_widths',replay_seconds=time.perf_counter()-t,verification=checks)
    except Timeout:r.update(status='replay_timeout' if phase=='replay' else 'producer_timeout',timeout_stage=phase)
    except ProofFailure as err:r.update(err.record)
    except Exception as err:r.update(status='error',error=repr(err),phase=phase,traceback=traceback.format_exc())
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    r.setdefault('producer_seconds',time.perf_counter()-start)
    r.update(total_seconds=time.perf_counter()-start,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    save(out/'cases'/(op+'.json'),r);print(mode,op,r['status'],r.get('states',''),r.get('leaves',''),round(r['producer_seconds'],3),flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--mode',choices=['composed','monolithic'],default='composed');ap.add_argument('--case');ap.add_argument('--cases',nargs='*');a=ap.parse_args()
    repo=setup(a.repo);check_baseline(repo)
    if a.case:case(a.case,repo,a.mode);return
    cases=a.cases or [x['case'] for x in json.loads((BASE/'CASES.json').read_text())]
    for op in cases:subprocess.run([sys.executable,str(Path(__file__).resolve()),'--repo',str(repo),'--mode',a.mode,'--case',op],check=True,timeout=130)
    rows=[json.loads((ROOT/'results'/a.mode/'cases'/(op+'.json')).read_text()) for op in cases]
    save(ROOT/'results'/a.mode/'summary.json',{'records':rows,'summary':dict(collections.Counter(r['status'] for r in rows)),'baseline_integrity':check_baseline(repo)})
    print(collections.Counter(r['status'] for r in rows))
if __name__=='__main__':main()
