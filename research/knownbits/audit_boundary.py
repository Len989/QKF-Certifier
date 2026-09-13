"""Post-experiment integrity, paired controls and complete result accounting."""
import collections,hashlib,json,platform,sys
from environment import ROOT,save
from freeze_boundary import verify

MODES=['previous','endpoints','boundary']


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def encoded(v):return len(json.dumps(v,sort_keys=True,separators=(',',':')).encode())


def audit_corpus(folder,mode,base):
    from corpus_io import names
    rows=read(folder/'summary.json')['records']
    assert sorted(r['case'] for r in rows)==names()
    cases=[];kinds=collections.Counter();statuses=collections.Counter();failures=collections.Counter();new_bytes=0;cells=0
    for row in rows:
        name=row['case'];p=row['producer'];r=row['replay']
        assert p==read(folder/'producer'/(name+'.json')) and r==read(folder/'replay'/(name+'.json'))
        assert r['status'] in {'proved_original_whole_all_positive_widths','all_preparations_and_available_proofs_replayed'}
        assert not r['search_modules_loaded'] and all(x['valid'] for x in r['component_width_one'])
        for k in ['sources','target','target_scope','budgets','component_count']:assert p[k]==base[name][k],(name,k)
        path=folder/'prepared'/(name+'.json');assert sha(path)==p['prepared_sha256'];prepared=read(path)
        assert set(prepared)==set(p['components'])==set(base[name]['components'])
        assert len(prepared)==r['components']==p['component_count']==p['final_component_count']
        proofs=sum('proof' in c for c in prepared.values())
        assert proofs==r['component_target_proofs']==sum(c['status']=='proved_component' for c in p['components'].values())
        new=0;queries=0;unresolved=0
        for c in prepared.values():
            for a in c['observation_attempts']:
                for q in a.get('boundary_queries',[]):
                    statuses[(q['engine'],q['status'])]+=1;queries+=1
                    if q['status']=='unresolved':failures[q['reason']]+=1;unresolved+=1
            for a in c['observation_rounds']:
                for t in a['trace']:
                    if not t['schema'].startswith('qkf-boundary-action-'):continue
                    kinds[t['proof']['kind']]+=1;new+=1;new_bytes+=encoded(t)
                    proof=t['proof'].get('boundary_proof',t['proof'])['derivation']
                    cells+=len(proof.get('cells',proof.get('observation',{}).get('supplied_cells',[])))
        cp=folder/'certificates'/(name+'.json');whole=p['status']=='certificate_produced'
        if whole:
            assert r['whole_verification'] and sha(cp)==p['certificate_sha256']
            assert read(cp)['components']==prepared and proofs==len(prepared)
        else:assert not cp.exists() and r['whole_verification'] is None
        if mode=='previous':
            for k in ['status','totals','symbolic_totals']:assert p[k]==base[name][k],(name,k)
            assert p.get('stopped_at')==base[name].get('stopped_at')
            for en,c in p['components'].items():
                for k in ['status','blockers','native_lemmas','action_rewrites','observation_rewrites']:assert c[k]==base[name]['components'][en][k],(name,en,k)
        stopped=p.get('stopped_at')
        stop_queries=[] if stopped is None else [q for a in prepared[stopped]['observation_attempts'] for q in a.get('boundary_queries',[])]
        cases.append(dict(case=name.removeprefix('KnownBits_'),status='proved_whole' if whole else p['status'],components=len(prepared),
            component_proofs=proofs,prepared_supported=sum(not c['blockers'] for c in p['components'].values()),
            stopped_at=stopped,obstruction=p['components'].get(stopped,{}).get('blockers'),stop_queries=stop_queries,
            producer_seconds=row['producer_wall_seconds'],replay_seconds=row['replay_wall_seconds'],
            seconds=row['producer_wall_seconds']+row['replay_wall_seconds'],states=p['totals']['states'],search_states=p['totals']['search_states'],
            transition_attempts=p['totals']['transition_attempts'],boundary_rewrites=new,boundary_queries=queries,
            certificate_bytes=p.get('certificate_bytes',0),prepared_bytes=p['prepared_bytes']))
    assert sum(r['components'] for r in cases)==411
    return dict(programs=39,components=411,whole_programs=[r['case'] for r in cases if r['status']=='proved_whole'],
        whole_count=sum(r['status']=='proved_whole' for r in cases),
        **{k:sum(r[k] for r in cases) for k in ['component_proofs','prepared_supported','seconds','producer_seconds','replay_seconds',
            'states','search_states','transition_attempts','boundary_rewrites','boundary_queries','certificate_bytes','prepared_bytes']},
        statuses=dict(collections.Counter(r['status'] for r in cases)),boundary_kinds=dict(kinds),boundary_trace_compact_bytes=new_bytes,
        supplied_action_cells=cells,query_statuses={e+':'+s:n for (e,s),n in statuses.items()},failures=dict(failures),records=cases,
        scope='all 411 preparations; target proof search stops at first failed component per program; counts are actual proofs, not an exhaustive attempt at every later component')


def audit_representations(folder):
    from boundary_cases import cases
    result={};declared=cases();assert len(declared)==320
    for mode in MODES:
        p=read(folder/mode/'producer.json')['records'];s=read(folder/mode/'summary.json')
        assert s['status']=='passed' and not s['search_modules_loaded'] and len(p)==s['cases']==len(declared)
        byrole=collections.defaultdict(lambda:dict(cases=0,supported=0))
        for source,saved,replayed in zip(declared,p,s['records']):
            for k in ['id','family','role','expression','reference']:assert json.dumps(source[k])==json.dumps(saved[k])
            assert replayed['supported']==saved['supported'] and replayed['id']==saved['id']
            byrole[source['role']]['cases']+=1;byrole[source['role']]['supported']+=saved['supported']
        assert sum(x['supported'] for x in p)==s['supported']
        assert len(s['families'])==80 and sum(f['all_supported'] for f in s['families'].values())==s['stable_supported_families']
        result[mode]={k:v for k,v in s.items() if k!='records'}
        result[mode].update(by_role=dict(byrole),producer_seconds=sum(r['producer_seconds'] for r in p),
            compiled_without_target_proof=True)
    return result


def main():
    n=verify();f2=read(ROOT/'FREEZE_V2.json')['files']
    for path,h in f2.items():assert sha(ROOT/path)==h,path
    baseline=read(ROOT/'BASELINE_SHA256.json')
    for path,h in baseline.items():assert sha(ROOT/path)==h,path
    v1=read(ROOT/'V1_RESULTS_SHA256.json')
    fresh='--fresh-results' in sys.argv
    if not fresh:
        for path,h in v1.items():assert sha(ROOT/path)==h,path
    base={r['case']:r['producer'] for r in read(ROOT/'baseline/summary.json')['records']}
    first={m:audit_corpus(ROOT/'results'/m,m,base) for m in MODES}
    second={'previous':first['previous']}
    second.update({m:audit_corpus(ROOT/'results_v2'/m,m,base) for m in ['endpoints','boundary']})
    result=dict(status='passed',freeze_v1_files=n,freeze_v2_files=len(f2),baseline_unchanged=len(baseline),v1_outputs_unchanged=None if fresh else len(v1),fresh_reproduction=fresh,
        corpus_v1=first,corpus_v2=second,representations_v1=audit_representations(ROOT/'results/representations'),
        representations_v2=audit_representations(ROOT/'results_v2/representations'),
        v2_corpus_control='previous reused from v1 without another run',actual_corpus_runs=5,
        actual_preparations_replayed=5*411,development=read(ROOT/'validation/development.json'),
        v2_development={k:v for k,v in read(ROOT/'validation/revision_v2_development.json').items() if k!='records'},
        no_new_external_holdout=True,no_new_smt_comparison=True)
    save(ROOT/'audit/AUDIT.json',result)
    save(ROOT/'audit/environment.json',dict(python=sys.version,platform=platform.platform(),machine=platform.machine(),
        dependencies='Python standard library only',solver_calls=False,repetitions=1))
    for v in ['v1','v2']:
        for m,r in result['corpus_'+v].items():print(v,m,{k:r[k] for k in ['whole_count','component_proofs','prepared_supported','seconds','boundary_rewrites','query_statuses']})
        for m,r in result['representations_'+v].items():print(v,m,'representations',r['supported'],'/320; families',r['stable_supported_families'])
    print('Audit passed; unchanged files:',n,len(f2),len(baseline),len(v1))


if __name__=='__main__':main()
