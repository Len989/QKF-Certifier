"""Serial fresh processes; immutable final outputs; strict replay bootstrap."""
import argparse,hashlib,json,resource,signal,subprocess,sys,time,traceback,types
from pathlib import Path
from environment import ROOT,save

SEARCH_MODULES={'result_v2_producer','result_v2_stage_producer','result_producer','result_stage_producer','context_stage_producer','context_producer','boundary_v2_stage_producer','semantic_choice_producer','row_observation_producer','selection_producer','observation_producer','external_producer','stage_producer','action_producer','native_producer','symbolic_producer',
 'producer','producer_v5','producer_v6','linear_search','corpus_discovery',
 'branch_producer','corpus_branch_producer','qkf_certifier.producer','qkf_certifier.api',
 'kernel_saturation','nonzero_ground','z3','cvc5','bitwuzla','boundary_producer','inference_producer','boundary_stage_producer','boundary_v2_producer'}


def final_save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    encoded=json.dumps(value,indent=2)+'\n'
    with path.open('x') as f:f.write(encoded)
    if json.loads(path.read_text())!=json.loads(encoded):raise ValueError('final serialization mismatch')


def strict_kernel():
    if 'qkf_certifier' in sys.modules:raise RuntimeError('checker bootstrap was too late')
    package=types.ModuleType('qkf_certifier')
    package.__path__=[str(ROOT/'public_runtime/src/qkf_certifier')]
    sys.modules['qkf_certifier']=package
    class NoSearch:
        def find_spec(self,fullname,path=None,target=None):
            if fullname in SEARCH_MODULES:raise ImportError('search blocked during replay: '+fullname)
    sys.meta_path.insert(0,NoSearch())
    import result_stage_kernel,regular_interfaces,prove_umin,guard_kernel,observer_kernel,mask_observers
    def disabled(*a,**kw):raise RuntimeError('search function disabled in replay')
    for m,n in [(regular_interfaces,'discover'),(prove_umin,'discover'),(guard_kernel,'produce'),(observer_kernel,'produce'),(mask_observers,'produce')]:setattr(m,n,disabled)
    return result_stage_kernel


def worker(args):
    start=time.perf_counter();out=args.output;case=args.case
    record=dict(case=case,mode=args.mode,phase=args.worker)
    def expired(*_):raise TimeoutError('60-second whole-program phase budget')
    signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,60)
    try:
        if args.worker=='producer':
            from result_v2_stage_producer import produce
            def checkpoint(r,p):
                save(out/'checkpoints'/(case+'.json'),dict(record=r,prepared=p))
            cert,r,prepared=produce(case,args.mode,checkpoint)
            from corpus_io import load
            _,fs,_=load(case)
            entries=[e for e in fs if e.startswith('partial_solution_') and not e.endswith(('_body','_cond'))] or ['solution']
            if set(prepared)!=set(entries) or set(r['components'])!=set(entries):raise ValueError('incomplete final preparations')
            for e,c in prepared.items():
                if ('proof' in c)!=(r['components'][e]['status']=='proved_component'):raise ValueError('component proof accounting')
            pp=out/'prepared'/(case+'.json');final_save(pp,prepared)
            record.update(r,prepared_sha256=hashlib.sha256(pp.read_bytes()).hexdigest(),
                          prepared_bytes=pp.stat().st_size,final_component_count=len(prepared))
            if cert is not None:
                cp=out/'certificates'/(case+'.json');final_save(cp,cert)
                record.update(certificate_sha256=hashlib.sha256(cp.read_bytes()).hexdigest(),certificate_bytes=cp.stat().st_size)
        else:
            kernel=strict_kernel()
            from corpus_io import load
            from regular_interfaces import target_for
            from branch_kernel import verify_tree
            from prove_umin import one_bit
            from word_oracle import evaluate
            producer=json.loads((out/'producer'/(case+'.json')).read_text())
            pp=out/'prepared'/(case+'.json')
            if hashlib.sha256(pp.read_bytes()).hexdigest()!=producer['prepared_sha256']:raise ValueError('prepared hash')
            prepared=json.loads(pp.read_text());bundle,fs,_=load(case)
            entries=[e for e in fs if e.startswith('partial_solution_') and not e.endswith(('_body','_cond'))] or ['solution']
            if set(prepared)!=set(entries):raise ValueError('expected all source entries')
            cp=out/'certificates'/(case+'.json');proofs=0;w1=[];whole=None
            if producer['status']=='certificate_produced':
                if hashlib.sha256(cp.read_bytes()).hexdigest()!=producer['certificate_sha256']:raise ValueError('certificate hash')
                cert=json.loads(cp.read_text())
                if cert['components']!=prepared:raise ValueError('prepared/certificate agreement')
                whole=kernel.verify(case,cert);proofs=len(entries)
            else:
                if cp.exists():raise ValueError('unexpected whole certificate')
                target,_=target_for(case)
                for entry,c in prepared.items():
                    final=kernel.replay_prepared(bundle,entry,c)
                    if 'proof' in c:
                        if target is None or c['proof']['backend']!='composed':raise ValueError('component target')
                        verify_tree(final,target,c['proof']['tree']);proofs+=1
                        _,bad=one_bit(fs,entry,target,evaluate)
                        w1.append(dict(entry=entry,valid=bad is None,counterexample=bad))
            loaded=sorted(SEARCH_MODULES.intersection(sys.modules))
            if loaded:raise ValueError('search modules loaded: '+repr(loaded))
            record.update(status='proved_original_whole_all_positive_widths' if whole else 'all_preparations_and_available_proofs_replayed',
                          components=len(entries),component_target_proofs=proofs,component_width_one=w1,
                          whole_verification=whole,search_modules_loaded=loaded,
                          action_rewrites=sum(len(r['trace']) for c in prepared.values() for r in c['action_rounds']),
                          observation_rewrites=sum(len(r['trace']) for c in prepared.values() for r in c['observation_rounds']),
                          native_symbolic_lemmas=sum(len(c['symbolic_trace']) for c in prepared.values()))
    except TimeoutError as e:
        record.update(status=args.worker+'_timeout',reason=str(e),accounting='interrupted work is only in checkpoint; no complete final claimed')
    except Exception as e:
        record.update(status='error',error=repr(e),traceback=traceback.format_exc())
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    record.update(seconds=time.perf_counter()-start,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    final_save(out/args.worker/(case+'.json'),record)
    print(args.mode,case,args.worker,record['status'],round(record['seconds'],3),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['baseline','sign','observed'],required=True)
    p.add_argument('--case');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--worker',choices=['producer','replay']);p.add_argument('--replay-only',action='store_true')
    a=p.parse_args();a.output=a.output.resolve()
    if a.worker:worker(a);raise SystemExit()
    from corpus_io import names
    records=[]
    for case in ([a.case] if a.case else names()):
        row=dict(case=case)
        for phase in (['replay'] if a.replay_only else ['producer','replay']):
            path=a.output/phase/(case+'.json')
            if path.exists():raise RuntimeError('final result already exists; use a fresh output directory')
            started=time.perf_counter()
            try:child=subprocess.run([sys.executable,str(ROOT/'result_v2_run.py'),'--case',case,'--mode',a.mode,'--output',str(a.output),'--worker',phase],timeout=70)
            except subprocess.TimeoutExpired:final_save(path,dict(case=case,status='hard_timeout'))
            if not path.exists():final_save(path,dict(case=case,status='worker_failure'))
            row[phase]=json.loads(path.read_text());row[phase+'_wall_seconds']=time.perf_counter()-started
            row['status']=row[phase]['status']
            if phase=='producer' and 'prepared_sha256' not in row[phase]:break
        records.append(row);save(a.output/'checkpoints/summary.json',dict(records=records))
    final_save(a.output/'summary.json',dict(records=records,programs=len(records)))
