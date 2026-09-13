"""Frozen development control, fresh source production and full strict replay."""
import argparse,hashlib,json,resource,signal,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent
NEW_SEARCH={'joint_producer','hull_producer','source_producer','z3','visibility_cc','certificates','countermodel'}


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def block_search():
    class Block:
        def find_spec(self,fullname,path=None,target=None):
            if fullname.split('.')[0] in NEW_SEARCH:raise ImportError('producer/solver blocked: '+fullname)
    sys.meta_path.insert(0,Block())


def worker(args):
    start=time.perf_counter();out=args.output;record=dict(mode=args.mode,operation=args.operation,phase=args.worker)
    def expired(*_):raise TimeoutError('60-second phase budget')
    signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,60)
    try:
        if args.worker=='source':
            source=(ROOT/'source/IntegerStamp.java').read_text()
            from source_kernel import SCHEMA,CONTRACT,observe_source
            if args.mode=='control':
                def unavailable(*_):raise ValueError('joint hull observation disabled by control')
                observed=observe_source(source,args.operation,unavailable)
                certificate=dict(schema=SCHEMA,operation=args.operation,contract=CONTRACT,source_observation=observed,hull_certificates=[])
            else:
                from source_producer import produce_source
                certificate=produce_source(source,args.operation)
            from ssa_emit import emit
            from mask_terms import tree
            expected=emit(tree(certificate['source_observation']['expression']))
            fixture=ROOT/'core/fixtures/corpus'/args.operation.capitalize()/'solution.mlir'
            if fixture.read_text()!=expected:raise ValueError('source/SSA observation binding')
            cp=out/'source_certificate.json';save(cp,certificate)
            record.update(status='source_observation_produced',source_certificate_sha256=sha(cp),source_certificate_bytes=cp.stat().st_size,
                          source_sha256=sha(ROOT/'source/IntegerStamp.java'),ssa_sha256=sha(fixture),
                          hull_calls=len(certificate['hull_certificates']),source_leaves=len(certificate['source_observation']['leaves']))
        elif args.worker=='replay':
            block_search()
            from source_kernel import replay_source
            from mask_terms import tree
            from ssa_emit import emit
            source=(ROOT/'source/IntegerStamp.java').read_text();producer=json.loads((out/'source.json').read_text())
            cp=out/'source_certificate.json'
            if sha(cp)!=producer['source_certificate_sha256']:raise ValueError('source certificate hash')
            certificate=json.loads(cp.read_text());observed=replay_source(source,args.operation,certificate)
            fixture=ROOT/'core/fixtures/corpus'/args.operation.capitalize()/'solution.mlir'
            if fixture.read_text()!=emit(tree(observed['expression'])):raise ValueError('final SSA differs from proved source observation')
            word_path=out/'word/certificates'/f'{args.operation.capitalize()}.json';word=json.loads(word_path.read_text())
            if word['sources']['program']!=sha(fixture) or word['target']!=args.operation:raise ValueError('word/source/target link')
            sys.path.insert(0,str(ROOT/'core'))
            import environment
            from result_v2_run import strict_kernel,SEARCH_MODULES
            verified=strict_kernel().verify(args.operation.capitalize(),word)
            if verified['status']!='proved_original_whole_all_positive_widths':raise ValueError('word target proof incomplete')
            loaded=sorted((set(sys.modules)&SEARCH_MODULES)|{n for n in sys.modules if n.split('.')[0] in NEW_SEARCH})
            if loaded:raise ValueError('search imports during replay: '+repr(loaded))
            record.update(status='proved_source_observation_and_whole_word_ssa',word_verification=verified,
                          source_leaves=len(observed['leaves']),hull_calls=observed['create_calls'],search_modules_loaded=loaded,
                          source_certificate_sha256=sha(cp),word_certificate_sha256=sha(word_path),ssa_sha256=sha(fixture),
                          mathematical_target='all positive word widths',source_execution_widths=[1,8,16,32,64],
                          native_boundary='Reviewed mask-hull loop/ordering lemma and previous source shims; no formal Java compiler proof.')
        elif args.worker=='joint':
            block_search()
            from joint_kernel import replay
            records=[]
            for path in sorted((ROOT/'validation/joint_v1').glob('certificate_*.json')):
                c=json.loads(path.read_text());r=replay(c['spec'],c['query'],c);records.append(dict(file=path.name,sha256=sha(path),result=r))
            loaded=[n for n in sys.modules if n.split('.')[0] in NEW_SEARCH]
            if loaded:raise ValueError(loaded)
            record.update(status='passed',certificates=len(records),search_modules_loaded=loaded,records=records)
        else:
            block_search()
            from theory_certificate import replay
            record.update(replay(json.loads((ROOT/'theory/certificate.json').read_text())))
            record['search_modules_loaded']=[n for n in sys.modules if n.split('.')[0] in NEW_SEARCH]
            if record['search_modules_loaded']:raise ValueError('ground search used during theory replay')
    except Exception as e:
        record.update(status='adapter_unsupported' if args.worker=='source' and isinstance(e,ValueError) else 'error',error=repr(e),traceback=traceback.format_exc())
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    record.update(seconds=time.perf_counter()-start,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    save(out/(args.worker+'.json'),record);print(args.mode,args.operation,args.worker,record['status'],flush=True)


def phase(mode,op,kind,out):
    out.mkdir(parents=True,exist_ok=True)
    command=[sys.executable,str(ROOT/'step_run.py'),'--worker',kind,'--mode',mode,'--operation',op,'--output',str(out)]
    try:subprocess.run(command,check=True,timeout=70)
    except (subprocess.TimeoutExpired,subprocess.CalledProcessError) as e:
        if not(out/(kind+'.json')).exists():save(out/(kind+'.json'),dict(status='worker_failure',error=repr(e)))
    return json.loads((out/(kind+'.json')).read_text())


def run():
    from freeze_step import verify
    print(verify(),flush=True);all_modes={}
    for mode in ['control','joint']:
        records=[]
        for op in ['and','or','xor','add','sub']:
            out=ROOT/'results'/mode/op;source=phase(mode,op,'source',out)
            row=dict(operation=op,source=source,status=source['status'])
            if source['status']=='source_observation_produced':
                subprocess.run([sys.executable,str(ROOT/'core/result_v2_run.py'),'--mode','observed','--case',op.capitalize(),'--output',str(out/'word')],check=True,timeout=150)
                word=json.loads((out/'word/summary.json').read_text())['records'][0];row['word']=word
                if word['status']=='proved_original_whole_all_positive_widths':
                    row['replay']=phase(mode,op,'replay',out);row['status']=row['replay']['status']
                else:row['status']='word_proof_incomplete'
            records.append(row)
        result=dict(selected=5,records=records);save(ROOT/'results'/mode/'summary.json',result);all_modes[mode]=result
    phase('joint','joint_queries','joint',ROOT/'results/strict_joint')
    phase('joint','paper_row','theory',ROOT/'results/strict_theory')
    print('UNCHANGED',verify(),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',choices=['source','replay','joint','theory']);p.add_argument('--mode',choices=['control','joint']);p.add_argument('--operation');p.add_argument('--output',type=Path);a=p.parse_args()
    if a.worker:a.output=a.output.resolve();worker(a)
    else:run()
