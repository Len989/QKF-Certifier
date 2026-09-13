"""Independent concrete-word oracles and exact Java execution, separate from the theorem."""
import itertools,json,random,time
from pathlib import Path
from native_upper import evaluate
from universal_api import CheckedUpperContract,signed
from universal_producer import produce
ROOT=Path(__file__).resolve().parent


def masks(width):
    for digits in itertools.product(range(3),repeat=width):
        must=sum((d==2)<<i for i,d in enumerate(digits));may=sum((d!=0)<<i for i,d in enumerate(digits))
        yield must,may


def words(width,must,may):
    optional=[1<<i for i in range(width) if (may&~must)>>i&1]
    values=[must]
    for bit in optional:values += [v|bit for v in values]
    return sorted(signed(v,width) for v in values)


def expected(spec,values):
    upper=[v for v in values if v<=spec['upper'] and (spec['can_zero'] or v!=0)]
    return max(upper) if upper else None


def run(out):
    out.mkdir(parents=True,exist_ok=False);start=time.perf_counter()
    source=(ROOT/'baseline/source/IntegerStamp.java').read_text();certificate=produce(source)['certificate']
    checked=CheckedUpperContract(source,certificate);small=[];wide=[];failures=[];samples=[];sentinels=dict(empty=0,actual_minimum=0)
    def check(spec,values,java_value=None,save=False):
        instance=checked.refine(spec);answer=instance['answer'];wanted=expected(spec,values);s=1<<(spec['width']-1)
        initial=[v for v in values if spec['lower']<=v<=spec['upper'] and (spec['can_zero'] or v!=0)]
        dest=instance['refined_spec'];after=[v for v in values if dest['lower']<=v<=dest['upper'] and (dest['can_zero'] or v!=0)]
        correct=(answer['maximum']==wanted and (answer['upper_query_status']=='empty')==(wanted is None)
                 and instance['joint_empty']==(not initial) and initial==after
                 and (java_value is None or java_value==(-s if wanted is None else wanted)))
        if not correct:failures.append(dict(spec=spec,expected=wanted,java=java_value,instance=instance,initial=initial,after=after))
        if java_value==-s:sentinels['empty' if wanted is None else 'actual_minimum']+=1
        if save:samples.append(dict(instance=instance,oracle_maximum=wanted,java_value=java_value))
        return instance
    for w in range(1,7):
        s=1<<(w-1);specs=[];word_sets=[]
        for must,may in masks(w):
            values=words(w,must,may)
            for u in range(-s,s):
                for zero in [False,True]:
                    specs.append(dict(width=w,must=must,may=may,lower=-s,upper=u,can_zero=zero));word_sets.append(values)
        outputs=evaluate(specs)
        for spec,values,answer in zip(specs,word_sets,outputs):check(spec,values,answer)
        small.append(dict(width=w,abstract_inputs=len(specs),java_calls=len(outputs)))
        print('exhaustive upper',w,len(specs),flush=True)
    rng=random.Random(2026091301)
    for w in [8,16,32,64,128,256,4096]:
        s=1<<(w-1);mask=(1<<w)-1;specs=[];word_sets=[];count=512 if w<=64 else 32
        for i in range(count):
            positions=set(rng.sample(range(w),min(8,w)))
            if i%2:positions.add(w-1)
            free=sum(1<<j for j in positions);must=rng.getrandbits(w)&~free;may=must|free;values=words(w,must,may)
            u=values[rng.randrange(len(values))] if i%3==0 else rng.randrange(-s,s)
            low=rng.randrange(-s,s)
            specs.append(dict(width=w,must=must,may=may,lower=low,upper=u,can_zero=bool(i%2)));word_sets.append(values)
        if w<=64:
            for must,may,u,zero in [(s,s,-s,False),(0,0,-1,True),(0,0,0,False),(0,mask,0,False)]:
                specs.append(dict(width=w,must=must,may=may,lower=-s,upper=u,can_zero=zero))
                word_sets.append([-1,0] if may==mask else words(w,must,may))
            # The full-mask case has a closed-form oracle maximum -1; the two
            # listed words suffice for this extra maximum/sentinel check.
            outputs=evaluate(specs)
        else:outputs=[None]*len(specs)
        for i,(spec,values,answer) in enumerate(zip(specs,word_sets,outputs)):
            check(spec,values,answer,save=i in {0,len(specs)-1})
        wide.append(dict(width=w,abstract_inputs=len(specs),java_calls=len(specs) if w<=64 else 0,
                         oracle='enumeration of at most 9 optional bits; one native full-mask analytic maximum where applicable'))
        print('wide upper',w,len(specs),flush=True)
    # Exhaust all lower/upper intersections separately. This is a check of
    # the new caller API, not a replacement for the universal preservation proof.
    refinement=[]
    for w in range(1,5):
        s=1<<(w-1);count=0
        for must,may in masks(w):
            values=words(w,must,may)
            for low in range(-s,s):
                for high in range(low,s):
                    for zero in [False,True]:
                        check(dict(width=w,must=must,may=may,lower=low,upper=high,can_zero=zero),values);count+=1
        refinement.append(dict(width=w,joint_inputs=count))
    diagnostics=[dict(width=4,must=1,may=13,lower=2,upper=7,can_zero=True),
                 dict(width=8,must=0,may=129,lower=-127,upper=0,can_zero=False),
                 dict(width=1,must=1,may=1,lower=-1,upper=-1,can_zero=False),
                 dict(width=1,must=0,may=0,lower=-1,upper=-1,can_zero=True)]
    for spec in diagnostics:check(spec,words(spec['width'],spec['must'],spec['may']),evaluate([spec])[0],save=True)
    result=dict(status='passed' if not failures else 'mismatches_preserved',exhaustive=small,
                exhaustive_upper_inputs=sum(r['abstract_inputs'] for r in small),wide=wide,
                wide_upper_inputs=sum(r['abstract_inputs'] for r in wide),
                java_calls=sum(r['java_calls'] for r in small+wide)+len(diagnostics),
                exact_joint_refinements=refinement,joint_refinement_inputs=sum(r['joint_inputs'] for r in refinement),
                sentinel_cases=sentinels,diagnostic_cases=len(diagnostics),failures=failures,
                seconds=time.perf_counter()-start,
                scope='Tests and Java execution are finite evidence; the separate source-bound induction/order certificate covers all input parameters and mathematical widths.')
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'development_certificate.json').write_text(json.dumps(certificate,indent=2)+'\n')
    for i,sample in enumerate(samples):(out/f'sample_{i:02d}.json').write_text(json.dumps(sample,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in {'wide','exhaustive','exact_joint_refinements','failures'}}),flush=True)
    if failures:raise ValueError('Semantic discrepancies preserved')
    return result


if __name__=='__main__':run(ROOT/'validation/semantics_v1')
