"""All declared representations, independent frozen producer/replay phases."""
import argparse,collections,hashlib,itertools,json,resource,subprocess,sys,time
from environment import ROOT,save


def produce_mode(mode):
    from representation_cases import cases
    from semantic_choice_producer import cover
    import observation_kernel as old
    results=[]
    for row in cases():
        t=time.perf_counter();e,g=row['expression'],row['guards'];r=dict(row,mode=mode)
        try:
            if mode=='previous':
                values,proof=old.support(e,g);cert=dict(engine='previous',values=values,proof=proof)
            else:
                cert=cover(e,g,mode);values=cert['certificate']['values'] if mode=='rows' else cert['values']
            r.update(status='covered',values=values,exact=values==row['expected'],certificate=cert)
        except ValueError as ex:r.update(status='unresolved',reason=str(ex))
        r['producer_seconds']=time.perf_counter()-t;results.append(r)
    save(ROOT/'results/representations'/mode/'producer.json',dict(records=results))


def replay_mode(mode):
    from inference_run import strict_kernel,SEARCH_MODULES
    strict_kernel()
    from representation_cases import cases
    from semantic_choice_kernel import verify_cover
    from qkf_certifier.kernel import digest
    from regular_interfaces import tree,order
    from word_oracle import expr_value
    import observation_kernel as old
    data=json.loads((ROOT/'results/representations'/mode/'producer.json').read_text());declared=cases();assert len(data['records'])==len(declared)
    verified=0;checks=0;rows=[]
    for saved,source in zip(data['records'],declared):
        for key in ['id','family','expression','guards','expected']:assert digest(saved[key])==digest(source[key])
        if saved['status']=='covered':
            e,g=source['expression'],source['guards'];c=saved['certificate']
            if mode=='previous':
                values,proof=old.support(e,g);assert digest(proof)==digest(c['proof']) and values==c['values']
            else:values=verify_cover(e,g,c)
            assert values==saved['values'];verified+=1
        e,g=source['expression'],source['guards'];nodes=order(e,*(p for p,t in g));arity=max([0]+[n[1] for n in nodes if n[0]=='var'])+1
        for w in [2,3,4]:
            image=set()
            for vals in itertools.product(range(1<<w),repeat=arity):
                if not all(bool(expr_value(p,list(vals),w))==t for p,t in g):continue
                value=expr_value(e,list(vals),w);image.add(value);checks+=1
                assert value in {v% (1<<w) for v in source['expected']},('reference image',source['id'])
                if saved['status']=='covered':assert value in {v% (1<<w) for v in saved['values']},('cover',source['id'])
            assert image=={v%(1<<w) for v in source['expected']},('reference image not realized',source['id'],w)
        rows.append(dict(id=saved['id'],family=saved['family'],status=saved['status'],exact=saved.get('exact',False),values=saved.get('values'),reason=saved.get('reason'),producer_seconds=saved['producer_seconds']))
    assert not SEARCH_MODULES.intersection(sys.modules)
    families={}
    for f in sorted(set(r['family'] for r in rows)):
        rs=[r for r in rows if r['family']==f]
        families[f]=dict(cases=len(rs),covered=sum(r['status']=='covered' for r in rs),exact=sum(r['exact'] for r in rs),
           stable_exact=all(r['exact'] for r in rs),distinct_covers=len({json.dumps(r['values']) for r in rs if r['status']=='covered'}))
    result=dict(status='passed',mode=mode,cases=len(rows),covered=verified,exact=sum(r['exact'] for r in rows),
       stable_exact_families=sum(r['stable_exact'] for r in families.values()),families=families,oracle_comparisons=checks,
       search_modules_loaded=[],records=rows)
    save(ROOT/'results/representations'/mode/'summary.json',result)
    print(mode,'cases',len(rows),'covered',verified,'exact',result['exact'],'stable families',result['stable_exact_families'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['previous','views','rows']);p.add_argument('--phase',choices=['producer','replay']);a=p.parse_args()
    if a.phase=='producer':produce_mode(a.mode)
    elif a.phase=='replay':replay_mode(a.mode)
    else:
        for mode in ['previous','views','rows']:
            for phase in ['producer','replay']:
                path=ROOT/'results/representations'/mode/('producer.json' if phase=='producer' else 'summary.json')
                if path.exists():raise ValueError('use a fresh experiment directory')
                t=time.perf_counter();proc=subprocess.run([sys.executable,str(ROOT/'representation_run.py'),'--mode',mode,'--phase',phase],timeout=60)
                if proc.returncode:raise SystemExit(proc.returncode)
