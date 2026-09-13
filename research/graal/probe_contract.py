"""Preserve the first native contract probe, including empty-set anomalies."""
import itertools,json
from pathlib import Path
from native_lower import evaluate
ROOT=Path(__file__).resolve().parent

def signed(x,w):return x-(1<<w) if x>>(w-1)&1 else x
def masks(w):
    for ds in itertools.product(range(3),repeat=w):
        yield sum((d==2)<<i for i,d in enumerate(ds)),sum((d!=0)<<i for i,d in enumerate(ds))
def words(w,m,y):
    values=[m]
    for i in range(w):
        if (y&~m)>>i&1:values += [v|(1<<i) for v in values]
    return sorted(signed(v,w) for v in values)
def run():
    out=ROOT/'development/initial_contract';out.mkdir(parents=True,exist_ok=False)
    rows=[];examples={};bad=[]
    for w in range(1,7):
        sign=1<<(w-1);specs=[];oracles=[]
        for m,y in masks(w):
            values=words(w,m,y)
            for low in range(-sign,sign):
                for zero in [False,True]:
                    specs.append(dict(width=w,must=m,may=y,lower=low,can_zero=zero))
                    feasible=[v for v in values if v>=low and (zero or v!=0)]
                    oracles.append(feasible[0] if feasible else None)
        outputs=evaluate(specs);counts=dict(nonempty=0,empty=0,nonempty_mismatch=0,empty_non_max_sentinel=0,returned_below_input=0)
        for s,o,v in zip(specs,oracles,outputs):
            key='nonempty' if o is not None else 'empty';counts[key]+=1
            if o is not None and v!=o:counts['nonempty_mismatch']+=1;bad.append(dict(spec=s,expected=o,actual=v))
            if o is None and v!=sign-1:
                counts['empty_non_max_sentinel']+=1
                exkey=f'w{w}:empty:{"outside" if not -sign<=v<sign else "inside"}'
                examples.setdefault(exkey,dict(spec=s,actual=v,expected_if_naive_contract=sign-1))
            if v<s['lower']:counts['returned_below_input']+=1
        rows.append(dict(width=w,calls=len(specs),**counts));print(rows[-1],flush=True)
    data=dict(status='completed',rows=rows,total=sum(r['calls'] for r in rows),nonempty_mismatches=bad,empty_counterexamples=examples,
              warning='A universal exact minimum on nonempty inputs is a different statement from a fixed MAX sentinel on empty inputs.')
    (out/'results.json').write_text(json.dumps(data,indent=2)+'\n')
if __name__=='__main__':run()
