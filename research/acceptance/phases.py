"""Separate shared-interface diagnostics, not extra end-to-end benchmark attempts."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time


def main():
    p=argparse.ArgumentParser(); p.add_argument('experiment',type=Path); p.add_argument('output',type=Path)
    p.add_argument('--root',type=Path,required=True); a=p.parse_args()
    sys.path.insert(0,str(a.root.resolve()))
    from research.signed_runtime.runtime import load
    from research.signed_targets.common import Monitor,prepare
    from research.signed_targets.producer import discover
    from research.signed_targets.checker import check_product,check_witness
    from research.signed_bridge.model import read
    from research.signed_predicates.semantics import evaluate
    spec=importlib.util.spec_from_file_location('run32_control',Path(__file__).with_name('control.py'))
    control=importlib.util.module_from_spec(spec); spec.loader.exec_module(control)
    data=json.loads((a.experiment/'cases/CASES.json').read_text()); rows={}
    for case in data['cases']:
        name=case['id']; proof=a.experiment/'attempts'/name/'closure_rows/discovery-0/proof.json'
        if not proof.exists() or case['group'].endswith('_control'): continue
        source=(a.experiment/'cases'/name/'source.java').read_text()
        target=json.loads((a.experiment/'cases'/name/'target.json').read_text())
        observations=json.loads(proof.read_text())['proof']['observations']
        compiled,selection=prepare(target); times=[]; finite=0
        for repeat in range(3):
            t=time.perf_counter(); runner,receipt=load(source,selection,observations)
            loading=time.perf_counter()-t
            row=Monitor(runner,compiled['specification'])
            t=time.perf_counter(); direct=control.DirectMonitor(runner,compiled['specification'],observations)
            extraction=time.perf_counter()-t
            record={'checked_load_seconds':loading,'control_copy_audit_seconds':extraction}
            obligations={}
            for mode,monitor in [('cells',direct),('rows',row)][::(1 if repeat%2==0 else -1)]:
                t=time.perf_counter(); obligation=discover(monitor,8192,4096)
                record[mode+'_product_discovery_seconds']=time.perf_counter()-t
                t=time.perf_counter()
                if obligation['kind']=='closure': check_product(monitor,obligation)
                else: check_witness(source,selection,monitor,obligation)
                record[mode+'_product_replay_seconds']=time.perf_counter()-t
                obligations[mode]=obligation
            if obligations['cells']!=obligations['rows']: raise ValueError('phase obligation mismatch')
            # Exactly the same outer loop/inputs for both action representations.
            words=[tuple(str(((i*6364136223846793005+1442695040888963407)&((1<<64)-1))>>b&1)
                         for b in range(64)) for i in range(2048)]
            def warm(action):
                answers=[]
                for word in words:
                    s=runner.machine.initial
                    for symbol in word: s=action(s,symbol)[1]
                    answers.append(runner.machine.terminal[s])
                return answers
            actions={'rows':runner.machine.step,'cells':lambda s,b:direct.table[s][int(b)]}
            values={}
            for mode in (('cells','rows') if repeat%2==0 else ('rows','cells')):
                t=time.perf_counter(); values[mode]=warm(actions[mode])
                record[mode+'_warm_seconds']=time.perf_counter()-t
            if values['cells']!=values['rows']: raise ValueError('warm action mismatch')
            times.append(record)
        ir=read(source,selection)
        # One separate finite correspondence pass per source, not 3x coverage.
        for width in range(1,9):
            for x in range(1<<width):
                state=runner.machine.initial
                for b in range(width): state=direct.table[state][x>>b&1][1]
                if (runner.machine.terminal[state]=='true')!=evaluate(ir,x,width) or runner.value(x,width)!=evaluate(ir,x,width):
                    raise ValueError('finite IR/cell/row mismatch')
                finite+=1
        rows[name]={'timings':times,'finite_ir_cell_row_comparisons':finite,
                    'classes':receipt['classes'],'stored_atoms':receipt['stored_atom_images'],
                    'product_kind':obligations['rows']['kind'],'shared_interface':True}
    result={'schema':'qkf-run32-phase-diagnostics-v1','cases':rows,'python':sys.version,
            'warm_inputs_per_case':2048,'warm_width':64,'repeats':3,
            'finite_comparisons':sum(r['finite_ir_cell_row_comparisons'] for r in rows.values()),
            'new_java_execution':False,'scope':'extra diagnostic stages; not included in end-to-end solver latency'}
    with a.output.open('x') as f: json.dump(result,f,sort_keys=True,indent=2); f.write('\n')
    print(json.dumps({'cases':len(rows),'finite_comparisons':result['finite_comparisons']}))


if __name__=='__main__': main()
