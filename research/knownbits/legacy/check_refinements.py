"""Check every saved refinement witness using direct whole-word semantics."""
from pathlib import Path
import argparse,json
from common import ROOT,BASE,setup,check_baseline,save

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,required=True);a=ap.parse_args();repo=setup(a.repo)
    from regular_interfaces import tree
    from qkf_certifier.kernel import digest
    from qkf_certifier.frontend import parse_bundle
    from branch_kernel import specialize
    from word_oracle import evaluate,expr_value,operation
    rows=[]
    for item in json.loads((BASE/'CASES.json').read_text()):
        op=item['case'];initial=tree(json.loads((ROOT/'results/composed/expressions'/(op+'.json')).read_text())['observed'])
        fs=parse_bundle({'program':(BASE/item['program']).read_text()})
        for leaf in json.loads((ROOT/'results/composed/leaves'/(op+'.json')).read_text()):
            path=tuple((tree(p),b) for p,b in leaf['path']);cur=specialize(initial,path)
            assert digest(cur)==leaf['expression_hash']
            for trial in leaf.get('guard_trials',[]):
                if trial['status']!='counterexample':continue
                witness=trial['witness'];w=witness['width'];m=(1<<w)-1
                v=witness['input_masks']+witness['concrete_inputs'];za,oa,zb,ob,x,y=v
                assert w>=2 and all(type(n) is int and 0<=n<=m for n in v)
                assert not za&oa and not zb&ob
                assert not x&za and x&oa==oa and not y&zb and y&ob==ob
                actual=[bool(expr_value(p,v,w)) for p,_ in path]
                violated=[i for i,(_,b) in enumerate(path) if actual[i]!=b]
                assert violated==witness['violated_path_literals'] and violated
                assert all(i not in violated for i in trial['assumption_indices'])
                target=min(x+y,m) if op=='uadd_sat' else max(x-y,0) if op=='usub_sat' else operation(op,[x,y],None,w)
                z,o=expr_value(cur,v,w)
                assert z&target or o&target!=o,('not a leaf counterexample',op,leaf['leaf'])
                full=evaluate(fs,[(za,oa),(zb,ob)],w)
                assert not full[0]&target and full[1]&target==full[1],('full source unsound',op)
                rows.append({'case':op,'leaf':leaf['leaf'],'width':w,'selected_premises':trial['assumption_indices'],
                             'violated_path_literals':violated,'specialized_masks':[z,o],'full_source_masks':list(full),'target_output':target})
    expected=sum(r['guard_refinements'] for r in json.loads((ROOT/'results/composed/summary.json').read_text())['records'])
    assert len(rows)==expected
    result={'status':'passed','witnesses_checked':len(rows),'widths':sorted({r['width'] for r in rows}),
            'every_witness_satisfies_current_proof_guard':True,'every_witness_violates_specialized_obligation':True,
            'every_witness_lies_outside_actual_source_path':True,'full_source_sound_at_every_witness':True,
            'records':rows,'baseline_integrity':check_baseline(repo)}
    save(ROOT/'results/refinement_witness_validation.json',result)
    print('Validated refinement counterexamples:',len(rows),'widths:',result['widths'])

if __name__=='__main__':main()
