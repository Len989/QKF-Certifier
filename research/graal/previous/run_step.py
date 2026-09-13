"""Fresh universal production, strict replay and unchanged five-slot Graal regression."""
import argparse,hashlib,json,resource,signal,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SEARCH={'universal_producer','sweep_producer','joint_producer','hull_producer','source_producer',
        'z3','visibility_cc','certificates','countermodel'}


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def block_search():
    class Block:
        def find_spec(self,fullname,path=None,target=None):
            if fullname.split('.')[0] in SEARCH:raise ImportError('Proof producer or solver blocked: '+fullname)
    sys.meta_path.insert(0,Block())


def worker(phase,out):
    start=time.perf_counter();record=dict(phase=phase)
    def expired(*_):raise TimeoutError('60-second proof phase budget')
    signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,60)
    try:
        if sys.flags.optimize:raise ValueError('Assertions must stay enabled')
        source=(ROOT/'baseline/source/IntegerStamp.java').read_text()
        if phase=='producer':
            from universal_producer import produce
            result=produce(source)
            if result['status']!='certificate_produced':raise ValueError(result)
            save(out/'certificate.json',result['certificate'])
            record.update(status='certificate_produced',source_sha256=sha(ROOT/'baseline/source/IntegerStamp.java'),
                          certificate_sha256=sha(out/'certificate.json'),certificate_bytes=(out/'certificate.json').stat().st_size)
        else:
            block_search()
            from universal_kernel import replay
            from universal_api import CheckedUpperContract
            producer=json.loads((out/'producer.json').read_text())
            if sha(out/'certificate.json')!=producer['certificate_sha256']:raise ValueError('Producer certificate hash')
            certificate=json.loads((out/'certificate.json').read_text());verified=replay(source,certificate)
            checked=CheckedUpperContract(source,certificate);samples=[]
            for path in sorted((ROOT/'validation/semantics_v2').glob('sample_*.json')):
                sample=json.loads(path.read_text());instance=sample['instance'];spec=instance['spec']
                samples.append(dict(file=path.name,sha256=sha(path),result=checked.verify_instance(spec,instance)))
            loaded=sorted(n for n in sys.modules if n.split('.')[0] in SEARCH)
            if loaded:raise ValueError('Search imported during replay: '+repr(loaded))
            record.update(status=verified['status'],verification=verified,source_sha256=producer['source_sha256'],
                          certificate_sha256=sha(out/'certificate.json'),search_modules_loaded=loaded,
                          specialized_instances=len(samples),instances=samples)
    except Exception as e:record.update(status='error',error=repr(e),traceback=traceback.format_exc())
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    record.update(seconds=time.perf_counter()-start,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    save(out/(phase+'.json'),record);print(phase,record['status'],flush=True)


def run(out):
    from freeze_step import verify
    initial=verify();out.mkdir(parents=True,exist_ok=False);proof_dir=out/'universal_upper';proof_dir.mkdir()
    for phase in ['producer','replay']:
        subprocess.run([sys.executable,str(ROOT/'run_step.py'),'--phase',phase,'--output',str(proof_dir)],check=True,timeout=70)
        result=json.loads((proof_dir/(phase+'.json')).read_text())
        if result['status']=='error':raise ValueError('Proof phase failed; details retained')
    subprocess.run([sys.executable,str(ROOT/'baseline/reproduce_main.py'),'--output',str(out/'graal_regression')],check=True,timeout=240)
    coverage={}
    for mode in ['control','joint']:
        records=json.loads((out/'graal_regression'/mode/'summary.json').read_text())
        if records['selected']!=5:raise ValueError('Changed Graal denominator')
        coverage[mode]=dict(selected=5,statuses={r['operation']:r['status'] for r in records['records']})
    if verify()!=initial:raise ValueError('Changed frozen version')
    result=dict(status='completed',integrity=initial,universal_upper='proved_all_inputs_and_mathematical_widths',
                specialized_instances=json.loads((proof_dir/'replay.json').read_text())['specialized_instances'],
                graal_regression=coverage,historical_NiceToMeetYou=dict(whole='11/39',components='104/411'),
                scope='One new universal helper contract; whole-program Graal denominator remains five. No new SMT run.')
    save(out/'results.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=['producer','replay']);p.add_argument('--output',type=Path,default=ROOT/'results/main');a=p.parse_args()
    out=a.output.resolve()
    if a.phase:worker(a.phase,out)
    else:run(out)
