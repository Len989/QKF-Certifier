"""Standalone isolated child: explicit engine root; no ambient research imports."""
import argparse
import builtins
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import sys
import time
import traceback


def canonical(v):
    return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def save(p,v):
    with p.open('xb') as f: f.write(canonical(v)+b'\n')


def metrics(mode,result,proof):
    inner=result.get('inner',{})
    result_metrics={'status':result['status'],'stage':inner.get('stage'),
                    'source_states':None,'classes':None,'positive_classes':None,
                    'observations':None,'product_states':None,'witness_width':None,
                    'proof_bytes':0 if proof is None else len(canonical(proof))+1}
    if proof is None:
        return result_metrics
    if mode=='frozen_v3':
        result_metrics.update(source_states=inner['native_states'],classes=inner['classes'],
                              observations=inner['selected_observations'],
                              product_states=inner.get('target_product_states'),
                              witness_width=inner.get('witness_width'))
    else:
        p=proof['proof']['observations']; t=inner['target']; r=inner['runtime']
        result_metrics.update(source_states=r['model_states_at_load'],classes=r['classes'],
                              positive_classes=r['positive_classes'],
                              observations=len(p['observations']['predicates']),
                              product_states=t.get('product_states'),witness_width=t.get('witness_width'),
                              interface_sha256=hashlib.sha256(canonical(p)).hexdigest(),
                              obligation_sha256=hashlib.sha256(canonical(proof['proof']['obligation'])).hexdigest())
    return result_metrics


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--case',type=Path,required=True)
    parser.add_argument('--mode',choices=('frozen_v3','closure_cells','closure_rows'),required=True)
    parser.add_argument('--operation',choices=('discover','check'),required=True)
    parser.add_argument('--budget',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--proof',type=Path)
    a=parser.parse_args(argv)
    root=a.root.resolve(); a.output.mkdir(parents=True,exist_ok=False)
    # -I excludes cwd/site environment path injection. The only research root is explicit.
    sys.path.insert(0,str(root))
    guard_active=a.operation=='check'
    if guard_active:
        original=builtins.__import__
        def guarded(name,*args,**kwargs):
            if 'producer' in name or name.split('.')[0] in {'subprocess','z3','cvc5','pysmt'}:
                raise RuntimeError('forbidden replay import: '+name)
            return original(name,*args,**kwargs)
        builtins.__import__=guarded
    try:
        if a.mode=='frozen_v3':
            from research.unified import v3 as engine
        elif a.mode=='closure_rows':
            from research.unified import v4 as engine
        else:
            spec=importlib.util.spec_from_file_location('run32_control',Path(__file__).with_name('control.py'))
            engine=importlib.util.module_from_spec(spec); spec.loader.exec_module(engine)
        source=(a.case/'source.java').read_text(encoding='utf-8')
        target=json.loads((a.case/'target.json').read_text())
        proof=json.loads(a.proof.read_text()) if a.proof else None
        wall,cpu=time.perf_counter(),time.process_time()
        if a.operation=='discover':
            result,proof=engine.prove(source,target,budgets=json.loads(a.budget))
        else:
            result=engine.check(source,target,proof)
        seconds=time.perf_counter()-wall; cpu_seconds=time.process_time()-cpu
        save(a.output/'result.json',result)
        if a.operation=='discover' and proof is not None: save(a.output/'proof.json',proof)
        origin={}
        for name,module in sorted(sys.modules.items()):
            if name=='research' or name.startswith(('research.','qkf_certifier.')) or name=='qkf_certifier':
                filename=getattr(module,'__file__',None)
                if filename:
                    path=Path(filename).resolve()
                    if not path.is_relative_to(root): raise RuntimeError('foreign engine import: '+name)
                    origin[name]={'path':path.relative_to(root).as_posix(),
                                  'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        save(a.output/'IMPORTS.json',origin)
        usage=resource.getrusage(resource.RUSAGE_SELF)
        record={'mode':a.mode,'operation':a.operation,'metrics':metrics(a.mode,result,proof),
                'result_sha256':hashlib.sha256(canonical(result)).hexdigest(),
                'operation_wall_seconds':seconds,'operation_cpu_seconds':cpu_seconds,
                'process_cpu_seconds':usage.ru_utime+usage.ru_stime,
                'process_peak_rss_kib':usage.ru_maxrss,'python':sys.version,
                'optimized':sys.flags.optimize,'guard_active':guard_active,
                'engine_root':str(root),'worker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        save(a.output/'RECORD.json',record)
        print(json.dumps(record,sort_keys=True)); return 0
    except Exception as exc:
        save(a.output/'ERROR.json',{'status':'internal_error','type':type(exc).__name__,
                                  'message':str(exc),'traceback':traceback.format_exc()})
        traceback.print_exc(); return 70


if __name__=='__main__':
    raise SystemExit(main())
