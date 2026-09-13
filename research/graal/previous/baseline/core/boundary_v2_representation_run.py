"""Frozen producer/replay comparison on every declared action representation."""
import argparse,json,subprocess,sys,time
from environment import ROOT,save

MODES=['previous','endpoints','boundary']


def prepare(e,mode):
    import mask_observers,action_producer,boundary_v2_producer
    cur=e;phases=[]
    nxt,t=mask_observers.produce(cur,2);phases.append(dict(kind='mask',trace=t,after=nxt));cur=nxt
    for _ in range(3):
        nxt,t,s=action_producer.produce(cur)
        if not t:break
        phases.append(dict(kind='action',trace=t,after=nxt));cur=nxt
        nxt,t=mask_observers.produce(cur,2);phases.append(dict(kind='mask',trace=t,after=nxt));cur=nxt
    for _ in range(3):
        nxt,t,s=boundary_v2_producer.produce(cur,mode)
        phases.append(dict(kind='observation',trace=t,stats=s,after=nxt));cur=nxt
        if not t:break
        nxt,t=mask_observers.produce(cur,2);phases.append(dict(kind='mask',trace=t,after=nxt));cur=nxt
        nxt,t,s=action_producer.produce(cur);phases.append(dict(kind='action',trace=t,after=nxt));cur=nxt
        nxt,t=mask_observers.produce(cur,2);phases.append(dict(kind='mask',trace=t,after=nxt));cur=nxt
    return dict(phases=phases,final=cur)


def produce(mode):
    from boundary_cases import cases
    from prefix_masks import supported
    records=[]
    for source in cases():
        started=time.perf_counter();c=prepare(source['expression'],mode)
        records.append(dict(source,certificate=c,supported=supported(c['final']),producer_seconds=time.perf_counter()-started))
    save(ROOT/'results_v2/representations'/mode/'producer.json',dict(records=records))


def replay(mode):
    from boundary_v2_run import strict_kernel,SEARCH_MODULES
    strict_kernel()
    from boundary_cases import cases
    from qkf_certifier.kernel import digest
    from regular_interfaces import tree,order
    from word_oracle import expr_value
    import mask_observers,action_kernel,boundary_v2_kernel
    from prefix_masks import supported
    import itertools,collections
    rows=json.loads((ROOT/'results_v2/representations'/mode/'producer.json').read_text())['records']
    declared=cases();assert len(rows)==len(declared)
    records=[];checks=0
    for saved,source in zip(rows,declared):
        for key in ['id','family','expression','reference','role']:assert digest(saved[key])==digest(source[key])
        cur=source['expression'];cert=saved['certificate']
        for phase in cert['phases']:
            nxt=tree(phase['after'])
            if phase['kind']=='mask':mask_observers.replay(cur,phase['trace'],nxt,2)
            elif phase['kind']=='action':action_kernel.replay(cur,phase['trace'],nxt)
            elif phase['kind']=='observation':boundary_v2_kernel.replay(cur,phase['trace'],nxt)
            else:raise AssertionError('phase')
            cur=nxt
        assert cur==tree(cert['final']) and supported(cur)==saved['supported']
        indices=sorted({n[1] for n in order(source['expression']) if n[0]=='var'})
        for w in [2,3,4]:
            for values in itertools.product(range(1<<w),repeat=len(indices)):
                vals=[0]*4
                for i,v in zip(indices,values):vals[i]=v
                a=expr_value(source['expression'],vals,w)
                assert a==expr_value(source['reference'],vals,w)==expr_value(cur,vals,w),(source['id'],w,vals)
                checks+=1
        records.append(dict(id=source['id'],family=source['family'],role=source['role'],supported=saved['supported'],
            final_hash=digest(cur),producer_seconds=saved['producer_seconds']))
    assert not SEARCH_MODULES.intersection(sys.modules)
    fs={}
    for f in sorted({r['family'] for r in records}):
        rs=[r for r in records if r['family']==f]
        fs[f]=dict(cases=len(rs),supported=sum(r['supported'] for r in rs),all_supported=all(r['supported'] for r in rs),
            distinct_final_forms=len({r['final_hash'] for r in rs}),role=rs[0]['role'])
    result=dict(status='passed',mode=mode,cases=len(records),supported=sum(r['supported'] for r in records),
        stable_supported_families=sum(f['all_supported'] for f in fs.values()),families=fs,
        original_value_comparisons=checks,search_modules_loaded=[],records=records,
        note='supported means accepted by the unchanged bit-relation grammar; does not mean a new whole-program target proof')
    save(ROOT/'results_v2/representations'/mode/'summary.json',result)
    print(mode,'cases',len(records),'supported',result['supported'],'families',result['stable_supported_families'],'comparisons',checks,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=MODES);p.add_argument('--phase',choices=['producer','replay']);a=p.parse_args()
    if a.phase=='producer':produce(a.mode)
    elif a.phase=='replay':replay(a.mode)
    else:
        for m in MODES:
            for phase in ['producer','replay']:
                expected=ROOT/'results_v2/representations'/m/('producer.json' if phase=='producer' else 'summary.json')
                if expected.exists():raise ValueError('use a fresh experiment directory')
                subprocess.run([sys.executable,str(ROOT/'boundary_v2_representation_run.py'),'--mode',m,'--phase',phase],check=True,timeout=180)
