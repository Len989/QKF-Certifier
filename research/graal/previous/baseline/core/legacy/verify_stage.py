"""Replay delivered certificates with proof search disabled; reject tampering."""
from pathlib import Path
import argparse,copy,json,signal,sys,time
from common import ROOT,BASE,setup,check_baseline,save

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,required=True);a=ap.parse_args();repo=setup(a.repo)
    import regular_interfaces,prove_umin,observer_kernel,guard_kernel,mask_observers
    from qkf_certifier import producer as old_producer
    from qkf_certifier.kernel import at,digest
    from regular_interfaces import tree
    from branch_kernel import specialize,guard
    from certificates import verify
    def forbidden(*args,**kwargs):raise AssertionError('proof search called during verification')
    for mod,name in [(regular_interfaces,'discover'),(prove_umin,'discover'),(observer_kernel,'produce'),(guard_kernel,'produce'),
                     (mask_observers,'produce'),(old_producer,'produce'),(old_producer,'normalize')]:setattr(mod,name,forbidden)
    assert 'branch_producer' not in sys.modules and 'z3' not in sys.modules
    stage=json.loads((ROOT/'STAGE.json').read_text());rows=[]
    def timeout(signum,frame):raise TimeoutError('independent replay exceeded 60 seconds')
    signal.signal(signal.SIGALRM,timeout)
    for item in json.loads((BASE/'CASES.json').read_text()):
        op=item['case'];p=ROOT/'results/composed/certificates'/(op+'.json');cert=json.loads(p.read_text())
        b={'program':(BASE/item['program']).read_text()};t=time.perf_counter();signal.setitimer(signal.ITIMER_REAL,60)
        try:counts=verify(b,cert,op)
        finally:signal.setitimer(signal.ITIMER_REAL,0)
        rows.append({'case':op,'status':'passed','seconds':time.perf_counter()-t,**counts});print(op,counts,'independently replayed',flush=True)
    # Use UMAX so failures target the new mask rules, actual source splitting,
    # and weakened-premise checking, rather than only old header checks.
    op='umax';source={'program':(BASE/'cases/umax.mlir').read_text()};original=json.loads((ROOT/'results/composed/certificates/umax.json').read_text())
    rejected=[]
    def reject(label,c,b=source,target=op):
        try:verify(b,c,target)
        except (ValueError,AssertionError,KeyError,IndexError,TypeError):rejected.append(label)
        else:raise AssertionError('invalid certificate accepted: '+label)
    bad=copy.deepcopy(original);bad['min_rewrite_width']=1;reject('width_partition_changed',bad)
    reject('different_source',original,{'program':source['program']+'\n'})
    reject('different_expected_target',original,target='umin')
    bad=copy.deepcopy(original);bad['mask_extension']='unknown';reject('unknown_mask_extension',bad)
    bad=copy.deepcopy(original);bad['composition_extension']='unknown';reject('unknown_composition_extension',bad)
    bad=copy.deepcopy(original);bad['mask_trace']=[];reject('missing_mask_compilation_proof',bad)
    bad=copy.deepcopy(original);bad['observed_hash']='0'*64;reject('different_compiled_source',bad)
    bad=copy.deepcopy(original);bad['proof'].pop('false');reject('missing_false_branch',bad)
    bad=copy.deepcopy(original);bad['proof']['false']=copy.deepcopy(bad['proof']['true']);reject('duplicated_true_branch',bad)
    bad=copy.deepcopy(original);bad['proof']['predicate_hash']='0'*64;reject('invented_case_predicate',bad)
    bad=copy.deepcopy(original);bad['proof']['select_path']=[];reject('split_at_nonselect',bad)
    initial=tree(original['observed'])
    def guarded_leaf(node,path=(),address=()):
        if node['kind']=='split':
            cur=specialize(initial,path);p=at(cur,node['select_path'])[1]
            found=guarded_leaf(node['true'],path+((p,True),),address+('true',))
            return found or guarded_leaf(node['false'],path+((p,False),),address+('false',))
        if node['kind']=='invariant' and node['assumption_indices']:return address,path
        return None
    address,path=guarded_leaf(original['proof'])
    def leaf(c):
        n=c['proof']
        for k in address:n=n[k]
        return n
    bad=copy.deepcopy(original);leaf(bad)['invariant']=[];reject('empty_leaf_invariant',bad)
    bad=copy.deepcopy(original);leaf(bad)['kind']='top';reject('nontrivial_leaf_as_top',bad)
    bad=copy.deepcopy(original);leaf(bad)['expression_hash']='0'*64;reject('wrong_specialized_expression',bad)
    bad=copy.deepcopy(original);leaf(bad)['guard_hash']='0'*64;reject('wrong_source_path_guard',bad)
    bad=copy.deepcopy(original);leaf(bad)['proof_guard_hash']='0'*64;reject('wrong_weakened_guard',bad)
    for label,indices in [('negative_guard_index',[-1]),('out_of_path_guard',[len(path)]),('boolean_guard_index',[True]),('duplicate_guard_index',[0,0])]:
        bad=copy.deepcopy(original);leaf(bad)['assumption_indices']=indices;reject(label,bad)
    bad=copy.deepcopy(original);leaf(bad)['assumption_indices']=[];leaf(bad)['proof_guard_hash']=digest(guard(()));reject('remove_required_premise_and_rehash',bad)
    bad=copy.deepcopy(original);bad['width_one'][0]['output']=[0,0];reject('different_width_one_output',bad)
    assert len(rows)==11 and len(rejected)==22
    result={'status':'passed','records':rows,'negative_certificates_rejected':rejected,'search_entry_points_disabled':7,'smt_loaded':False,'branch_producer_loaded':False,'baseline_integrity':check_baseline(repo)}
    save(ROOT/'results/independent_verification.json',result);print('All 11 replayed; rejected mutations:',len(rejected))
if __name__=='__main__':main()
