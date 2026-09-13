"""Fresh strict replay: no producer, search or SMT module is needed."""
import json
from pathlib import Path
from carry_kernel import require,digest,replay as replay_carry
from lower_source import compile_source
from lower_order import replay as replay_order,CONCLUSION
from sweep_kernel import replay as replay_sweep
SCHEMA='qkf-universal-conditional-lower-v1'

def replay(source,c):
    require(set(c)=={'schema','compiled_source','sweep','successor','outer','contract'},'lower certificate fields')
    require(c['schema']==SCHEMA and c['contract']==CONCLUSION,'conditional lower contract')
    compiled=compile_source(source);require(c['compiled_source']==compiled,'full source binding')
    sweep=replay_sweep(compiled['sweep_guard'],c['sweep'])
    successor=replay_carry(compiled['carry_program'],c['successor'])
    outer=replay_order(compiled['outer_ir'],c['outer'])
    return dict(status='proved_universal_conditional_lower_contract',certificate_sha256=digest(c),sweep=sweep,successor=successor,outer=outer,
                conclusion=CONCLUSION,trust_boundary='Restricted source bridge, native mask/CodeUtil and least-positive-word lemmas, finite induction kernel, Python runtime. No formally verified Java compiler or proof-assistant claim.')

if __name__=='__main__':
    import argparse,sys
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--certificate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if sys.flags.optimize:raise ValueError('Assertions must remain enabled')
    class BlockSearch:
        def find_spec(self,fullname,path=None,target=None):
            if any(t in fullname for t in ['producer','z3','pysmt']):raise ImportError('Search blocked in strict lower replay: '+fullname)
    sys.meta_path.insert(0,BlockSearch())
    result=replay(a.source.read_text(),json.loads(a.certificate.read_text()))
    result['search_modules_loaded']=[n for n in sys.modules if any(t in n for t in ['producer','z3','pysmt'])]
    require(not result['search_modules_loaded'],'strict checker imported search')
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['status','certificate_sha256','search_modules_loaded']}))
