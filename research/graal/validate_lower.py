"""All small native inputs, sparse wide words, and exact additional range intersections."""
import json,random,time
from pathlib import Path
from probe_contract import masks,words
from native_lower import evaluate
from lower_producer import produce
from lower_api import CheckedLowerContract,execute_concrete,sign_admissible
ROOT=Path(__file__).resolve().parent

def run():
    out=ROOT/'validation/semantics';out.mkdir(parents=True,exist_ok=False);start=time.perf_counter()
    source=(ROOT/'previous/baseline/source/IntegerStamp.java').read_text();c=produce(source)['certificate'];api=CheckedLowerContract(source,c)
    counts=dict(inputs=0,admitted=0,unsupported=0,exact_minimum=0,conservative_bound=0,empty=0,java_calls=0)
    rows=[];samples=[];failures=[]
    def check(s,values,native=None,save=False):
        counts['inputs']+=1;actual=execute_concrete(s)['source_long_result']
        if native is not None:
            counts['java_calls']+=1
            if native!=actual:failures.append(dict(reason='interpreter/native mismatch',spec=s,interpreter=actual,native=native))
        record=api.refine(s)
        if not sign_admissible(s):
            counts['unsupported']+=1
            if record['status']!='unsupported_source_sign_context':failures.append(dict(reason='unsafe input not refused',spec=s))
        else:
            counts['admitted']+=1;counts[record['precision']]+=1
            before=[v for v in values if s['lower']<=v<=s['upper'] and (s['can_zero'] or v!=0)]
            after=[v for v in values if actual<=v<=s['upper'] and (s['can_zero'] or v!=0)]
            if before!=after or record['joint_empty']!=(not before) or (record['precision']=='exact_minimum' and record['minimum']!=min(before)):
                failures.append(dict(reason='refinement mismatch',spec=s,before=before,after=after,record=record))
            if record['precision']=='conservative_bound' and (not before or not(s['lower']<=actual<min(before))):
                failures.append(dict(reason='false conservative classification',spec=s,record=record))
        if save:samples.append(dict(spec=s,record=record,oracle_words=values,native=native))
    for w in range(1,7):
        sign=1<<(w-1);specs=[];value_sets=[];before=dict(counts)
        for m,a in masks(w):
            vals=words(w,m,a)
            for low in range(-sign,sign):
                for zero in [False,True]:specs.append(dict(width=w,must=m,may=a,lower=low,upper=sign-1,can_zero=zero));value_sets.append(vals)
        for s,v,j in zip(specs,value_sets,evaluate(specs)):check(s,v,j)
        rows.append(dict(group='exhaustive_native',width=w,**{k:counts[k]-before[k] for k in counts}));print(rows[-1],flush=True)
    rng=random.Random(2026091302)
    for w in [8,16,32,64,128,256,4096]:
        sign=1<<(w-1);specs=[];value_sets=[];before=dict(counts)
        for i in range(512 if w<=64 else 32):
            free=sum(1<<j for j in rng.sample(range(w),min(w,8)))
            if i%2:free|=sign
            m=rng.getrandbits(w)&~free;a=m|free
            if i%3==0:m&=sign-1;a&=sign-1
            vals=words(w,m,a);low=vals[rng.randrange(len(vals))] if i%4==0 else rng.randrange(-sign,sign)
            if i%3==1:low=min(low,0)
            high=rng.randrange(-sign,sign)
            specs.append(dict(width=w,must=m,may=a,lower=low,upper=high,can_zero=bool(i%2)));value_sets.append(vals)
        diagnostics=[(0,0,0,False),(0,sign,-1,False),(sign,sign,-sign,False),
                     (1,sign|1,0,True),(0,(1<<(w-2))|1,2,True),
                     ((sign-1)&~((1<<(w-2))|1),sign-1,sign//2-1,True)]
        for m,a,low,zero in diagnostics:
            specs.append(dict(width=w,must=m,may=a,lower=low,upper=sign-1,can_zero=zero));value_sets.append(words(w,m,a))
        natives=evaluate(specs) if w<=64 else [None]*len(specs)
        for i,(s,v,j) in enumerate(zip(specs,value_sets,natives)):check(s,v,j,save=i==0 or i>=len(specs)-len(diagnostics))
        rows.append(dict(group='sparse_wide_native' if w<=64 else 'sparse_mathematical_lift',width=w,**{k:counts[k]-before[k] for k in counts}));print({k:v for k,v in rows[-1].items() if k in {'group','width','inputs','admitted','java_calls'}},flush=True)
    for w in range(1,5):
        sign=1<<(w-1);before=dict(counts)
        for m,a in masks(w):
            vals=words(w,m,a)
            for low in range(-sign,sign):
                for high in range(-sign,sign):
                    for zero in [False,True]:check(dict(width=w,must=m,may=a,lower=low,upper=high,can_zero=zero),vals)
        rows.append(dict(group='all_lower_upper_intersections',width=w,**{k:counts[k]-before[k] for k in counts}));print({k:v for k,v in rows[-1].items() if k in {'group','width','inputs','admitted'}},flush=True)
    result=dict(status='passed' if not failures else 'failed',counts=counts,groups=rows,failures=failures,seconds=time.perf_counter()-start,
                scope='Finite semantic checks; all-width claims come from separate source-bound row/induction/order certificates. Wide oracles enumerate at most nine optional bits. Native production widths are 1,8,16,32,64; other <=64 widths are helper diagnostics.')
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');(out/'certificate.json').write_text(json.dumps(c,indent=2)+'\n')
    for i,s in enumerate(samples):(out/f'sample_{i:02}.json').write_text(json.dumps(s,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],counts=counts,failures=len(failures),seconds=result['seconds'])),flush=True)
    if failures:raise ValueError('Semantic failures saved')
if __name__=='__main__':run()
