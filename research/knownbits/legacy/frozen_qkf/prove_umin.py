#!/usr/bin/env python3
"""Uniform corpus run: new checked observer identities, unchanged targets/backend."""
from pathlib import Path
import argparse,collections,copy,itertools,json,pickle,sys,time
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'dependencies'))
from regular_interfaces import (discover,check_invariant,tree,order,
                                target_expression,word_target,KB,LETTERS,COMPS)
from prefix_masks import Machine,lower,shape,BACKEND
from audit_fixed import validate_freeze
SCHEMA='qkf-observer-component-v1'
WHOLE_SCHEMA='qkf-observer-whole-v1'


class WorkBudget(Exception):pass


class LengthMachine(Machine):
    def __init__(self,e,target,attempt_budget=None):
        self.attempts=0;self.attempt_budget=attempt_budget
        super().__init__(e,target)
        self.initial=tuple((0,*s) for s in self.initial);self.bound*=2
    def step(self,state,letter,end,right_guess):
        self.attempts+=1
        if self.attempt_budget is not None and self.attempts>self.attempt_budget:raise WorkBudget()
        return super().step(state,letter,end,right_guess)
    def successors(self,state,end):
        if end and state[0]==0:return
        for li,g,(nxt,out,y) in super().successors(state[1:],end):
            yield li,g,((1,*nxt),out,y)


def initial_guesses(e,target):
    return shape(e,target)['initial_states']


def one_bit(fs,entry,target,evaluate):
    rows=[]
    for ka,kb in itertools.product(KB,repeat=2):
        z,o=evaluate(fs,[ka,kb],1,entry)
        rows.append({'inputs':[ka,kb],'output':[z,o]})
        for a,b in itertools.product((0,1),repeat=2):
            if a&ka[0] or a&ka[1]!=ka[1] or b&kb[0] or b&kb[1]!=kb[1]:continue
            y=word_target(target,a,b,1)
            if y&z or y&o!=o:
                return rows,{'width':1,'input_masks':list(ka+kb),'concrete_inputs':[a,b],
                             'target_output':y,'candidate_masks':[z,o]}
    return rows,None


def witness(fs,entry,target,letters,evaluate):
    ls=[LETTERS[i] for i in letters];w=len(ls)
    vals=[sum(row[i]<<j for j,row in enumerate(ls)) for i in range(6)]
    output=evaluate(fs,[tuple(vals[:2]),tuple(vals[2:4])],w,entry)
    y=word_target(target,vals[4],vals[5],w)
    if not(output[0]&y or output[1]&y!=output[1]):raise ValueError('nonconcrete witness')
    return {'width':w,'input_masks':vals[:4],'concrete_inputs':vals[4:],'target_output':y,'candidate_masks':list(output)}


def verify_component(bundle,entry,cert,target):
    from qkf_certifier.frontend import parse_bundle
    from qkf_certifier.kernel import replay as public_replay,CONTRACT,digest
    from guard_kernel import replay
    from observer_kernel import replay as observer_replay,EXTENSION
    from word_oracle import evaluate
    if cert['schema']!=SCHEMA or cert['target']!=target or cert['entry']!=entry:raise ValueError('entry/target/schema')
    if cert['semantics']!=CONTRACT or cert['min_rewrite_width']!=2:raise ValueError('contract/width')
    if cert['backend']!=BACKEND:raise ValueError('backend mismatch')
    if cert['extension']!=EXTENSION:raise ValueError('observer extension mismatch')
    if cert['normalization']['entry']!=entry:raise ValueError('normalization entry')
    nf=public_replay(bundle,entry,cert['normalization']);simple=tree(cert['simplified'])
    replay(nf,cert['rewrites'],simple,2)
    if digest(simple)!=cert['simplified_hash']:raise ValueError('simplified expression hash')
    observed=tree(cert['observed']);observer_replay(simple,cert['observer_trace'],observed,2)
    if digest(observed)!=cert['observed_hash']:raise ValueError('observed expression hash')
    if digest(lower(observed))!=cert['compiled_hash']:raise ValueError('compiled expression hash')
    rows,bad=one_bit(parse_bundle(bundle),entry,target,evaluate)
    if bad is not None or json.loads(json.dumps(rows))!=cert['width_one']:raise ValueError('width one not proved')
    return check_invariant(LengthMachine(observed,target),cert['invariant'])


def composition(fs,entries,expression):
    f=fs['solution'];inputs=[('input',0),('input',1)];env=dict(zip(f['args'],inputs));called=set();meet_checked=False
    for dst,op,args,callee in f['ops']:
        if op!='call':raise ValueError('unsupported solution skeleton')
        xs=[env[a] for a in args]
        if callee in entries:
            if xs!=inputs:raise ValueError('component arguments changed')
            env[dst]=frozenset([callee]);called.add(callee)
        elif callee=='meet':
            if not meet_checked:
                if expression(fs,'meet')!=('pair',('or',('var',0),('var',2)),('or',('var',1),('var',3))):raise ValueError('actual meet mismatch')
                meet_checked=True
            if len(xs)!=2 or not all(isinstance(x,frozenset) for x in xs):raise ValueError('meet arguments')
            env[dst]=xs[0]|xs[1]
        else:raise ValueError('uncertified callee '+callee)
    if env[f['return']]!=set(entries) or called!=set(entries):raise ValueError('component coverage')
    return sorted(called)


def verify_whole(bundle,manifest,certificates,target):
    from qkf_certifier.frontend import parse_bundle,expression
    from qkf_certifier.kernel import hashes
    from observer_kernel import EXTENSION
    if manifest['schema']!=WHOLE_SCHEMA or manifest['backend']!=BACKEND:raise ValueError('whole schema/backend')
    if manifest['extension']!=EXTENSION:raise ValueError('whole observer extension')
    if manifest['target']!=target or manifest['sources']!=hashes(bundle):raise ValueError('whole target/source')
    if set(manifest['components'])!=set(certificates):raise ValueError('missing component proof')
    checks=sum(verify_component(bundle,entry,c,target) for entry,c in certificates.items())
    used=composition(parse_bundle(bundle),certificates,expression)
    if used!=manifest['composition']:raise ValueError('wrong composition')
    return checks


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--repo',type=Path,required=True)
    ap.add_argument('--results',type=Path,default=ROOT/'results');args=ap.parse_args()
    repo=args.repo.resolve();frozen=validate_freeze(repo);out=args.results
    sys.path[:0]=[str(repo/'src'),str(repo/'tests')]
    from qkf_certifier.frontend import parse_bundle,expression
    from qkf_certifier.kernel import CONTRACT,digest,hashes
    from word_oracle import evaluate
    from observer_kernel import EXTENSION
    with (out/'local_cache.pkl').open('rb') as f:cache=pickle.load(f)
    component_items=[x for x in cache if x['record']['role']=='component']
    bundle_by_op={x['record']['operator']:x['bundle'] for x in cache}
    fs_by_op={op:parse_bundle(bundle) for op,bundle in bundle_by_op.items()}
    cert_dir=out/'certificates';cert_dir.mkdir(exist_ok=True)
    started=time.perf_counter();records=[];certs_by_op=collections.defaultdict(dict)
    for item in component_items:
        a=item['record'];op=a['operator'];entry=a['entry'];target=a['target'];fs=fs_by_op[op]
        r={k:a[k] for k in ('operator','entry','target','target_scope','regular_before','regular_after','regular_without_prefix','regular_without_observers','additional_rewrites','observer_rewrites','observer_rules','blockers','run_nodes')}
        t=time.perf_counter()
        if target is None:r['status']='unsupported_target'
        else:
            width_one,bad=one_bit(fs,entry,target,evaluate)
            if bad is not None:r.update({'status':'counterexample_width_one','witness':bad})
            elif not a['regular_after']:r['status']='unsupported_candidate'
            elif initial_guesses(item['observed'],target)>frozen['state_budget_per_component']:
                r.update({'status':'initial_state_budget','initial_guesses':initial_guesses(item['observed'],target)})
            elif shape(item['observed'],target)['nonterminal_attempts_per_state']>frozen['transition_attempt_budget_per_component']:
                r.update({'status':'branching_budget','shape':shape(item['observed'],target)})
            else:
                machine=LengthMachine(item['observed'],target,frozen['transition_attempt_budget_per_component'])
                try:proof=discover(machine,frozen['state_budget_per_component'])
                except WorkBudget:proof={'status':'transition_attempt_budget'}
                r['transition_attempts']=machine.attempts
                if proof['status']=='counterexample':
                    r.update({'status':'counterexample_width_ge_two','witness':witness(fs,entry,target,proof['letters'],evaluate),
                              'states_explored':proof['states_explored']})
                elif proof['status']=='proved_sound':
                    cert={'schema':SCHEMA,'backend':BACKEND,'extension':EXTENSION,'semantics':CONTRACT,'entry':entry,'target':target,'min_rewrite_width':2,
                          'normalization':item['normalization'],'rewrites':item['rewrites'],'simplified':item['simple'],
                          'simplified_hash':digest(item['simple']),'observed':item['observed'],
                          'observed_hash':digest(item['observed']),'observer_trace':item['observer_trace'],
                          'compiled_hash':digest(lower(item['observed'])),
                          'invariant':proof['states'],'width_one':width_one}
                    cert=json.loads(json.dumps(cert));checks=verify_component(item['bundle'],entry,cert,target)
                    name=op+'__'+entry+'.json';(cert_dir/name).write_text(json.dumps(cert,separators=(',',':'))+'\n')
                    certs_by_op[op][entry]=cert
                    r.update({'status':'proved_sound','states':proof['state_count'],'valid_transition_checks':checks,'certificate':'certificates/'+name})
                else:r.update({'status':proof['status'],**{k:v for k,v in proof.items() if k!='status'}})
        r['seconds']=time.perf_counter()-t;records.append(r)
        if target is not None:
            print(op,entry,r['status'],r.get('states',r.get('states_explored','')),flush=True)
        (out/'proofs.partial.json').write_text(json.dumps(records,indent=2)+'\n')
    whole_records=[];whole_checks=whole_concrete=0
    for op in sorted(bundle_by_op):
        rs=[r for r in records if r['operator']==op];target=rs[0]['target'];fs=fs_by_op[op]
        wrec={'operator':op,'target':target,'target_scope':rs[0]['target_scope'],'component_count':len(rs),
              'proved_components':sum(r['status']=='proved_sound' for r in rs),
              'component_status_counts':dict(collections.Counter(r['status'] for r in rs))}
        try:used=composition(fs,{r['entry'] for r in rs},expression);wrec['actual_composition_verified']=True
        except ValueError as ex:used=None;wrec['actual_composition_verified']=False;wrec['composition_reason']=str(ex)
        if all(r['status']=='proved_sound' for r in rs) and used is not None:
            manifest={'schema':WHOLE_SCHEMA,'backend':BACKEND,'extension':EXTENSION,'sources':hashes(bundle_by_op[op]),'target':target,
                      'components':{r['entry']:r['certificate'] for r in rs},'composition':used}
            checks=verify_whole(bundle_by_op[op],manifest,certs_by_op[op],target)
            name=op+'__whole.json';(cert_dir/name).write_text(json.dumps(manifest,indent=2)+'\n')
            wrec.update({'status':'proved_original_whole','certificate':'certificates/'+name,'checked_transitions':checks})
            for width in range(1,5):
                for rows in itertools.product(KB,repeat=2*width):
                    vals=[sum(rows[2*j+i//2][i%2]<<j for j in range(width)) for i in range(4)]
                    ka,kb=tuple(vals[:2]),tuple(vals[2:]);z,o=evaluate(fs,[ka,kb],width,'solution');whole_checks+=1
                    for a,b in itertools.product(range(1<<width),repeat=2):
                        if a&ka[0] or a&ka[1]!=ka[1] or b&kb[0] or b&kb[1]!=kb[1]:continue
                        y=word_target(target,a,b,width);assert not y&z and y&o==o;whole_concrete+=1
        else:
            wrec['status']='unsupported_target' if target is None else 'not_proved'
            # A component witness persists through meet; verify it on actual full SSA.
            witness_row=next((r for r in rs if 'witness' in r),None)
            if witness_row is not None and used is not None:
                wit=witness_row['witness'];v=wit['input_masks'];w=wit['width'];a,b=wit['concrete_inputs']
                z,o=evaluate(fs,[tuple(v[:2]),tuple(v[2:])],w,'solution');y=word_target(target,a,b,w)
                assert y&z or y&o!=o
                wrec.update({'status':'explicit_target_refuted','witness':dict(wit,candidate_masks=[z,o]),'witness_from_component':witness_row['entry']})
        whole_records.append(wrec)
    # Check distinct source-binding and composition failures using the Smax proof.
    op='KnownBits_Smax';b=bundle_by_op[op];entry='partial_solution_8';c=certs_by_op[op][entry];rejections=[]
    def reject(label,bundle,cert,expected='smax'):
        try:verify_component(bundle,entry,cert,expected)
        except (ValueError,AssertionError):rejections.append(label)
        else:raise AssertionError('changed certificate accepted')
    bad=copy.deepcopy(c);bad['invariant']=[];reject('empty_invariant',b,bad)
    bad_bundle=dict(b);bad_bundle['program']+='\n';reject('different_source',bad_bundle,c)
    reject('different_expected_target',b,c,'umax')
    op_prefix='KnownBits_Umin';entry_prefix='partial_solution_0'
    if entry_prefix in certs_by_op[op_prefix]:
        for label,field,value in [('different_compiled_expression','compiled_hash','0'*64),
                                  ('different_backend','backend','unrecognized-backend')]:
            bad=copy.deepcopy(certs_by_op[op_prefix][entry_prefix]);bad[field]=value
            try:verify_component(bundle_by_op[op_prefix],entry_prefix,bad,'umin')
            except ValueError:rejections.append(label)
            else:raise AssertionError('changed prefix certificate accepted')
    manifest=json.loads((cert_dir/(op+'__whole.json')).read_text());incomplete=dict(certs_by_op[op]);incomplete.pop(entry)
    try:verify_whole(b,manifest,incomplete,'smax')
    except ValueError:rejections.append('missing_component')
    else:raise AssertionError('incomplete composition accepted')
    uop='KnownBits_Umin';ue='partial_solution_6'
    if ue in certs_by_op[uop]:
        uc=certs_by_op[uop][ue];ub=bundle_by_op[uop]
        for label,field,value in [('missing_observer_rewrites','observer_trace',[]),
                                  ('different_observer_extension','extension','unrecognized-extension'),
                                  ('width_partition_changed','min_rewrite_width',1)]:
            bad=copy.deepcopy(uc);bad[field]=value
            try:verify_component(ub,ue,bad,'umin')
            except ValueError:rejections.append(label)
            else:raise AssertionError('changed Umin certificate accepted')
        um=json.loads((cert_dir/(uop+'__whole.json')).read_text());incomplete=dict(certs_by_op[uop]);incomplete.pop(ue)
        try:verify_whole(ub,um,incomplete,'umin')
        except ValueError:rejections.append('missing_umin_component')
        else:raise AssertionError('incomplete Umin accepted')
    result={'configuration':frozen,'backend':BACKEND,'extension':EXTENSION,'semantics':CONTRACT,'component_summary':dict(collections.Counter(r['status'] for r in records)),
            'whole_summary':dict(collections.Counter(r['status'] for r in whole_records)),
            'whole_abstract_regressions_width_1_to_4':whole_checks,'whole_concrete_regressions_width_1_to_4':whole_concrete,
            'rejected_changes':rejections,'records':records,'whole_records':whole_records,'elapsed_seconds':time.perf_counter()-started,
            'scope':'New observer identities layered over unchanged earlier rewrite and count-mask modules; unchanged targets. Flag-family targets are stronger unconditional obligations, not original poison/precondition contracts.'}
    (out/'proofs.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('records','whole_records','configuration')},indent=2))


if __name__=='__main__':main()
