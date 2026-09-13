"""Account for every original component, strict replay and inherited control."""
import collections,hashlib,io,json,platform,sys,tarfile,zipfile
from environment import ROOT,save
from freeze_result import verify
from corpus_io import load,names
from qkf_certifier.kernel import digest,hashes
from regular_interfaces import order,tree
from prefix_masks import lower,allowed_node

PRIOR='QKF_CONTEXT_OBSERVATIONS_2026-09-13.zip'
PRIOR_SHA='4d2d70618c7fc663569b9b44fbfba280e020268119e70e6695c29f796f1622fa'
OLD_ROOT='qkf_context_observations_2026-09-13/'


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def verify_prior():
    prior=ROOT/'prior_stage'/PRIOR
    if sha(prior)!=PRIOR_SHA:raise ValueError('exact prior archive changed')
    baseline=read(ROOT/'baseline/summary.json');old_hashes=read(ROOT/'baseline/final_hashes.json')
    with zipfile.ZipFile(prior) as z:
        data_manifest=json.loads(z.read(OLD_ROOT+'DATA_MANIFEST.json'))
        packed=z.read(OLD_ROOT+'EXPERIMENT_DATA.tar.xz')
        assert hashlib.sha256(packed).hexdigest()==data_manifest['archive_sha256']
        with tarfile.open(fileobj=io.BytesIO(packed),mode='r:xz') as tar:
            def old(n):
                b=tar.extractfile(n).read();r=data_manifest['files'][n]
                assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256']
                return json.loads(b)
            assert old('results/context/summary.json')==baseline
            for name in names():
                prepared=old('results/context/prepared/'+name+'.json')
                assert {e:c['final_hash'] for e,c in prepared.items()}==old_hashes[name]
                assert all(digest(c['final'])==c['final_hash'] for c in prepared.values())
    return baseline,old_hashes


def audit():
    frozen=verify();baseline,old_hashes=verify_prior()
    baseline_records={r['case']:r for r in baseline['records']}
    modes={};matrix={name:dict(case=name) for name in names()};output_hashes={}
    for mode in ['baseline','sign','observed']:
        rs=read(ROOT/'results'/mode/'summary.json')['records']
        assert [r['case'] for r in rs]==names()
        result=dict(whole=[],component_proofs=0,prepared=0,prepared_supported=0,
            new_rewrites=collections.Counter(),interface_rules=collections.Counter(),
            result_requests=collections.Counter(),producer_statuses=collections.Counter(),
            producer_seconds=0,replay_seconds=0,certificate_bytes=0,
            replayed_preparations=0,search_modules_loaded=[],programs=len(names()))
        for r in rs:
            case=r['case'];p=r['producer'];v=r['replay'];bundle,fs,_=load(case)
            entries=[e for e in fs if e.startswith('partial_solution_') and not e.endswith(('_body','_cond'))] or ['solution']
            assert p['sources']==hashes(bundle)
            for key in ['budgets','target','target_scope']:
                assert p[key]==baseline_records[case]['producer'][key],(case,key)
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
            else:
                assert not (ROOT/'results'/mode/'certificates'/(case+'.json')).exists()
            if mode=='baseline':
                assert p['status']==baseline_records[case]['producer']['status']
                for entry,c in prepared.items():
                    assert c['final_hash']==old_hashes[case][entry]
                    assert p['components'][entry]['status']==baseline_records[case]['producer']['components'][entry]['status']
            supported=0;new=[]
            for entry,c in prepared.items():
                assert digest(c['final'])==c['final_hash']
                blockers=dict(collections.Counter(n[0] for n in order(lower(tree(c['final']))) if not allowed_node(n)))
                assert blockers==p['components'][entry]['blockers'];supported+=not bool(blockers)
                for rnd in c['observation_rounds']:
                    for t in rnd['trace']:
                        if t['schema']!='qkf-requested-result-observation-v1':continue
                        assert mode!='baseline' and (mode!='sign' or t['kind']=='sign')
                        kind=t['kind'];result['new_rewrites'][kind]+=1
                        for step in t['proof']['interface']['steps']:result['interface_rules'][step['rule']]+=1
                        new.append(dict(entry=entry,kind=kind,source_hash=t['proof']['source_hash']))
                for attempt in c['observation_attempts']:
                    for q in attempt.get('result_requests',[]):result['result_requests'][q['kind']+'/'+q['status']]+=1
            result['component_proofs']+=proved;result['prepared']+=len(entries)
            result['prepared_supported']+=supported;result['replayed_preparations']+=v['components']
            result['producer_statuses'][p['status']]+=1
            for phase in ['producer','replay']:result[phase+'_seconds']+=r[phase]['seconds']
            result['certificate_bytes']+=p.get('certificate_bytes',0)
            matrix[case][mode]=dict(whole=whole,proved=proved,components=len(entries),supported=supported,
                status=p['status'],stopped_at=p.get('stopped_at'),new_rewrites=new,
                stopped_blockers=p['components'].get(p.get('stopped_at'),{}).get('blockers',{}))
        assert result['prepared']==result['replayed_preparations']==411
        result['whole_count']=len(result['whole']);modes[mode]=result
        for path in (ROOT/'results'/mode).rglob('*'):
            if path.is_file():output_hashes[str(path.relative_to(ROOT))]=sha(path)
    tests=read(ROOT/'validation/frozen/results.json')
    development=read(ROOT/'validation/development_v2/results.json')
    assert tests['status']==development['status']=='passed'
    assert {k:v for k,v in tests.items() if k!='seconds'}=={k:v for k,v in development.items() if k!='seconds'}
    keys=['cases','representation_checks','exhaustive_signed_division_checks','exhaustive_high_divisor_checks','contextual_checks','corruptions_rejected']
    assert [tests[k] for k in keys]==[304,233472,87376,88392,7371,315]
    regressions=[c for c,m in matrix.items() if m['observed']['proved']<m['baseline']['proved'] or (m['baseline']['whole'] and not m['observed']['whole'])]
    summary=dict(status='passed',freeze=frozen,prior_archive_sha256=PRIOR_SHA,
        baseline_identical_final_expressions=411,modes=modes,matrix=list(matrix.values()),
        mechanism_tests={**{k:tests[k] for k in keys},'carrier_refusals':len(tests['refusals']),
                         'separating_inputs':len(tests['separating_inputs'])},
        unchanged_targets_contracts_and_budgets=True,strict_replay_processes=117,
        regressions=regressions,new_whole=sorted(set(modes['observed']['whole'])-set(modes['baseline']['whole'])),
        interpretation='known development corpus; proofs stop at first component failure; grammar-supported preparations are not target proofs')
    save(ROOT/'audit/AUDIT.json',summary)
    save(ROOT/'audit/FINAL_OUTPUTS_SHA256.json',output_hashes)
    save(ROOT/'audit/environment.json',dict(python=sys.version,platform=platform.platform(),machine=platform.machine()))
    return summary


if __name__=='__main__':
    a=audit();keys=['whole_count','component_proofs','prepared_supported','producer_seconds','replay_seconds','new_rewrites']
    print(json.dumps(dict(status=a['status'],regressions=a['regressions'],
        modes={k:{x:v[x] for x in keys} for k,v in a['modes'].items()}),indent=2))
