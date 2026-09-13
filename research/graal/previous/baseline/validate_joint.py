"""Independent concrete-set oracle, malformed proofs, and large sparse words."""
import copy,itertools,json,random,time
from pathlib import Path
from joint_producer import produce
from joint_kernel import replay
ROOT=Path(__file__).resolve().parent


def masks(w):
    for digits in itertools.product(range(3),repeat=w):
        yield sum(1<<k for k,d in enumerate(digits) if d==2),sum(1<<k for k,d in enumerate(digits) if d!=0)


def concrete(spec,candidates=None):
    w=spec['width'];s=1<<(w-1)
    values=[x for x in (range(1<<w) if candidates is None else candidates)
            if spec['lower']<=(x-(1<<w) if x&s else x)<=spec['upper'] and x&spec['must']==spec['must'] and x&~spec['may']==0 and (spec['can_zero'] or x!=0)]
    must=(1<<w)-1;may=0
    for x in values:must&=x;may|=x
    order=sorted(x-(1<<w) if x&s else x for x in values)
    return values,dict(count=len(values),lower=order[0] if values else None,upper=order[-1] if values else None,
                       must=must if values else 0,may=may,zero=0 in values,word=values[0] if len(values)==1 else None)


def check(spec,values,expected,bit_checks):
    q={'kind':'summary'};c=produce(spec,q);assert replay(spec,q,c)['answer']==expected
    for k in bit_checks:
        q={'kind':'bit','index':k};proof=produce(spec,q);a=replay(spec,q,proof)['answer'];support=sum(1<<v for v in {x>>k&1 for x in values})
        assert a['support']==support and all(x in values and x>>k&1==int(v) for v,x in a['witnesses'].items())
    return c


def run(out):
    out.mkdir(parents=True,exist_ok=False);start=time.perf_counter();counts=[];saved=[]
    for w in range(1,5):
        s=1<<(w-1);n=bits=0
        for must,may in masks(w):
            for low in range(-s,s):
                for high in range(low,s):
                    for zero in [False,True]:
                        spec=dict(width=w,must=must,may=may,lower=low,upper=high,can_zero=zero)
                        values,expected=concrete(spec);which=list(range(w)) if len(values)<=2 else [w-1]
                        check(spec,values,expected,which);n+=1;bits+=len(which)
        counts.append(dict(width=w,summaries=n,bit_queries=bits));print('exhaustive',w,n,bits,flush=True)
    rng=random.Random(20260913);wide=[]
    for w in [8,16,32,64,128,256]:
        s=1<<(w-1);n=0
        for _ in range(128):
            free=rng.sample(range(w),min(8,w));must=rng.getrandbits(w)&~sum(1<<k for k in free);may=must|sum(1<<k for k in free)
            candidates=[must|sum((1<<k) for i,k in enumerate(free) if bits>>i&1) for bits in range(1<<len(free))]
            low,high=sorted([rng.randrange(-s,s),rng.randrange(-s,s)])
            spec=dict(width=w,must=must,may=may,lower=low,upper=high,can_zero=bool(rng.randrange(2)))
            values,expected=concrete(spec,candidates);proof=check(spec,values,expected,[0,w-1,rng.randrange(w)])
            if n<2:saved.append(proof)
            n+=1
        wide.append(dict(width=w,summaries=n,enumerated_free_bits=8));print('wide',w,n,flush=True)
    for w in [1,4,8,64,256,4096]:
        s=1<<(w-1);mask=(1<<w)-1
        for zero in [False,True]:
            spec=dict(width=w,must=0,may=mask,lower=-s,upper=s-1,can_zero=zero)
            proof=produce(spec,{'kind':'summary'});a=replay(spec,{'kind':'summary'},proof)['answer']
            assert a['count']==(1<<w)-int(not zero) and len(proof['cells'])==1
            if w>1:assert a['must']==0 and a['may']==mask
            saved.append(proof)
    example=dict(width=4,must=1,may=13,lower=2,upper=7,can_zero=True)
    positive=produce(example,{'kind':'bit','index':2});assert replay(example,positive['query'],positive)['answer']=={'support':2,'witnesses':{'1':5}}
    saved.append(positive);saved.append(produce(example,{'kind':'summary'}))
    negative=[]
    def reject(label,proof,spec=None,query=None):
        try:replay(example if spec is None else spec,positive['query'] if query is None else query,proof)
        except (ValueError,TypeError,IndexError,KeyError):negative.append(label)
        else:raise AssertionError('accepted invalid certificate: '+label)
    p=copy.deepcopy(positive);p['answer']['support']=3;reject('invented opposite bit',p)
    p=copy.deepcopy(positive);p['answer']['witnesses']['1']=1;reject('word from weak independent interface',p)
    p=copy.deepcopy(positive);p['cells']=p['cells'][:-1];reject('missing interval cell',p)
    p=copy.deepcopy(positive);p['cells'][0]['start']+=1;reject('shifted cover',p)
    p=copy.deepcopy(positive);p['cells'][0]['observation']['count']+=1;reject('invented cell cardinality',p)
    p=copy.deepcopy(positive);p['joins'][0]['right']=p['joins'][0]['left'];reject('duplicated union support',p)
    p=copy.deepcopy(positive);p['joins'][0]['left']=99999;reject('future union premise',p)
    reject('changed source bounds',positive,spec={**example,'lower':0})
    reject('changed requested bit',positive,query={'kind':'bit','index':1})
    reject('boolean width masquerading as integer',positive,spec={**example,'width':True})
    for spec in [dict(width=4,must=3,may=1,lower=-8,upper=7,can_zero=True),dict(width=4,must=0,may=15,lower=7,upper=-8,can_zero=True)]:
        proof=produce(spec,{'kind':'empty'});assert replay(spec,proof['query'],proof)['answer']['empty'];saved.append(proof)
    for i,c in enumerate(saved):
        (out/f'certificate_{i:02d}.json').write_text(json.dumps(c,indent=2)+'\n')
    result=dict(status='passed',exhaustive=counts,exhaustive_summaries=sum(r['summaries'] for r in counts),
                exhaustive_bit_queries=sum(r['bit_queries'] for r in counts),wide=wide,wide_summaries=sum(r['summaries'] for r in wide),
                large_analytic_cases=12,negative_checks=negative,saved_certificates=len(saved),seconds=time.perf_counter()-start,
                scope='Each certificate covers all words of one concrete abstract input. It is not a universal transformer theorem over all input masks.')
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':run(ROOT/'validation/joint_v1')
