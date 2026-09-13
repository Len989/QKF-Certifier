"""All five known Graal slots remain in the development denominator."""
import hashlib,json,time,traceback
from pathlib import Path
from source_producer import produce_source
from source_kernel import replay_source,body
from ssa_emit import emit
from mask_terms import tree
ROOT=Path(__file__).resolve().parent


if __name__=='__main__':
    source=(ROOT/'source/IntegerStamp.java').read_text();records=[]
    for op in ['and','or','xor','add','sub']:
        start=time.perf_counter();out=ROOT/'cases'/op;out.mkdir(parents=True,exist_ok=False)
        row=dict(operation=op,source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                 body_sha256=hashlib.sha256(body(source,op)[1].encode()).hexdigest())
        try:
            certificate=produce_source(source,op);observed=replay_source(source,op,certificate)
            ssa=emit(tree(observed['expression']));name=op.capitalize();path=ROOT/'core/fixtures/corpus'/name/'solution.mlir';path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('x') as f:f.write(ssa)
            (out/'development_source_certificate.json').write_text(json.dumps(certificate,indent=2)+'\n')
            row.update(status='admitted',qkf_case=name,ssa_path=str(path.relative_to(ROOT)),ssa_sha256=hashlib.sha256(ssa.encode()).hexdigest(),
                       expression=observed['expression'],source_leaves=len(observed['leaves']),hull_calls=observed['create_calls'])
        except Exception as e:
            row.update(status='adapter_unsupported',reason=repr(e))
            (out/'unsupported.json').write_text(json.dumps(dict(error=repr(e),traceback=traceback.format_exc()),indent=2)+'\n')
        row['development_seconds']=time.perf_counter()-start;records.append(row);print(op,row['status'],flush=True)
    (ROOT/'CASES.json').write_text(json.dumps(dict(schema='qkf-joint-development-selection-v1',selected=5,
             previous_frozen_coverage='1/5 unchanged historical control',cases=records),indent=2)+'\n')
