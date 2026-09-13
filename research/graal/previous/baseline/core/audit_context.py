"""Post-run accounting, exact old-control comparison, and package evidence."""
import collections,hashlib,json,platform,sys,zipfile
from pathlib import Path
from environment import ROOT,save
from freeze_context import verify
from corpus_io import load,names
from qkf_certifier.kernel import digest,hashes
from regular_interfaces import order,tree
from prefix_masks import lower,allowed_node

PRIOR='QKF_BOUNDARY_ACTIONS_2026-09-13.zip'
PRIOR_SHA='a231c3fa18bde0c28149cb098d6006f0b29ee186e9a2c37b6310ed9de1245884'
OLD_ROOT='qkf_boundary_actions_2026-09-13/'


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def audit():
    frozen=verify();prior=ROOT/'prior_stage'/PRIOR
    assert sha(prior)==PRIOR_SHA
    with zipfile.ZipFile(prior) as z:
        old={n:json.loads(z.read(OLD_ROOT+'results_v2/boundary/prepared/'+n+'.json')) for n in names()}
        old_manifest=json.loads(z.read(OLD_ROOT+'PACKAGE_MANIFEST.json'))
        for n in names():
            name='results_v2/boundary/prepared/'+n+'.json'
            assert hashlib.sha256(z.read(OLD_ROOT+name)).hexdigest()==old_manifest['files'][name]['sha256']
    baseline=read(ROOT/'baseline/summary.json')
    baseline_records={r['case']:r for r in baseline['records']}
    modes={};matrix={name:dict(case=name) for name in names()};all_output_hashes={}
    for mode in ['baseline','guards','context']:
        rs=read(ROOT/'results'/mode/'summary.json')['records']
        assert [r['case'] for r in rs]==names()
        result=dict(whole=[],component_proofs=0,prepared=0,prepared_supported=0,
            new_rewrites=collections.Counter(),sparse_origins=collections.Counter(),
            context_requests=collections.Counter(),producer_statuses=collections.Counter(),
            producer_seconds=0,replay_seconds=0,certificate_bytes=0,original_components=0,
            replayed_preparations=0,search_modules_loaded=[],programs=39)
        for r in rs:
            case=r['case'];p=r['producer'];v=r['replay'];bundle,fs,_=load(case)
            entries=[e for e in fs if e.startswith('partial_solution_') and not e.endswith(('_body','_cond'))] or ['solution']
            assert p['sources']==hashes(bundle)
            assert p['budgets']==baseline_records[case]['producer']['budgets']
            assert p['target']==baseline_records[case]['producer']['target']
            assert p['target_scope']==baseline_records[case]['producer']['target_scope']
            pp=ROOT/'results'/mode/'prepared'/(case+'.json');prepared=read(pp)
            assert sha(pp)==p['prepared_sha256'] and set(prepared)==set(entries)
            assert v['search_modules_loaded']==[] and v['components']==len(entries)
            assert v['status'] in {'proved_original_whole_all_positive_widths','all_preparations_and_available_proofs_replayed'}
            proved=sum('proof' in c for c in prepared.values())
            assert proved==v['component_target_proofs']==sum(c['status']=='proved_component' for c in p['components'].values())
            assert all(w['valid'] for w in v['component_width_one'])
            whole=v['status']=='proved_original_whole_all_positive_widths'
            assert whole==(p['status']=='certificate_produced')
            if whole:
                assert proved==len(entries);result['whole'].append(case)
                cp=ROOT/'results'/mode/'certificates'/(case+'.json')
                assert sha(cp)==p['certificate_sha256'] and read(cp)['components']==prepared
            if mode=='baseline':
                assert p['status']==baseline_records[case]['producer']['status']
                for entry,c in prepared.items():
                    assert c['final_hash']==old[case][entry]['final_hash']
                    assert digest(c['final'])==digest(old[case][entry]['final'])
                    assert p['components'][entry]['status']==baseline_records[case]['producer']['components'][entry]['status']
            supported=0;new=[]
            for entry,c in prepared.items():
                assert digest(c['final'])==c['final_hash']
                blockers=dict(collections.Counter(n[0] for n in order(lower(tree(c['final']))) if not allowed_node(n)))
                assert blockers==p['components'][entry]['blockers']
                supported+=not bool(blockers)
                for rnd in c['observation_rounds']:
                    for t in rnd['trace']:
                        if t['schema']!='qkf-scoped-count-observation-v1':continue
                        assert mode!='baseline' and t['policy']==mode
                        kind=t['proof']['kind'];result['new_rewrites'][kind]+=1
                        cover=t['proof'].get('cover',{})
                        if 'origin' in cover:result['sparse_origins'][cover['origin']]+=1
                        new.append(dict(entry=entry,kind=kind,source_hash=t['proof']['source_hash']))
                for a in c['observation_attempts']:
                    for q in a.get('context_requests',[]):result['context_requests'][q['status']]+=1
            result['component_proofs']+=proved;result['prepared']+=len(entries)
            result['prepared_supported']+=supported;result['original_components']+=len(entries)
            result['replayed_preparations']+=v['components']
            result['producer_statuses'][p['status']]+=1
            for phase in ['producer','replay']:result[phase+'_seconds']+=r[phase]['seconds']
            result['certificate_bytes']+=p.get('certificate_bytes',0)
            matrix[case][mode]=dict(whole=whole,proved=proved,components=len(entries),supported=supported,
                status=p['status'],stopped_at=p.get('stopped_at'),new_rewrites=new,
                stopped_blockers=p['components'].get(p.get('stopped_at'),{}).get('blockers',{}))
        assert result['prepared']==result['original_components']==result['replayed_preparations']==411
        result['whole_count']=len(result['whole']);modes[mode]=result
        for p in (ROOT/'results'/mode).rglob('*'):
            if p.is_file():all_output_hashes[str(p.relative_to(ROOT))]=sha(p)
    reps=read(ROOT/'validation/frozen_representations/results.json')
    assert reps['status']=='passed' and reps['cases']==416 and reps['families']==104
    assert reps['missing_premise_refusals']==832 and all(r['missing_guard_refused'] and r['missing_contract_refused'] for r in reps['records'])
    consumers=read(ROOT/'validation/frozen_consumers/results.json')
    dev=read(ROOT/'validation/development_v2/development.json')
    assert consumers['status']==dev['status']=='passed' and consumers['cases']==73
    assert len(dev['rejected_corruptions'])==19 and consumers['rejected']==79
    summary=dict(status='passed',freeze=frozen,prior_archive_sha256=PRIOR_SHA,
        baseline_identical_final_expressions=411,modes=modes,matrix=list(matrix.values()),
        mechanism_tests=dict(representations=reps['cases'],families=reps['families'],representation_checks=reps['finite_random_checks'],
            removed_premises_refused=reps['missing_premise_refusals'],consumer_cases=consumers['cases'],consumer_checks=consumers['finite_random_checks'],
            development_checks=dev['checks'],corruptions_refused=consumers['rejected']+len(dev['rejected_corruptions']),
            separating_inputs=len(consumers['separating_inputs'])+len(dev['separating_inputs'])),
        unchanged_targets_contracts_and_budgets=True,strict_replay_processes=117,
        interpretation='component counts stop at first failure; supported preparations are not target proofs')
    save(ROOT/'audit/AUDIT.json',summary)
    save(ROOT/'audit/FINAL_OUTPUTS_SHA256.json',all_output_hashes)
    save(ROOT/'audit/environment.json',dict(python=sys.version,platform=platform.platform(),machine=platform.machine()))
    return summary


if __name__=='__main__':
    a=audit()
    keys=['whole_count','component_proofs','prepared_supported','producer_seconds','replay_seconds','new_rewrites']
    print(json.dumps(dict(status=a['status'],modes={k:{x:v[x] for x in keys} for k,v in a['modes'].items()}),indent=2))
