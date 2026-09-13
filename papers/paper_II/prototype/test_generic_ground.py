import random, sys
from engine import Term,const,build_pool,close,depth
from visibility_cc import VisibilityCongruenceClosure

random.seed(424242)
ops={'f':1,'g':2}
C=[const('c0'),const('c1')]
T0=build_pool(ops,C,0,0)
T1=build_pool(ops,C,1,0)
T2=build_pool(ops,C,2,0)
byD={0:T0,1:T1,2:T2}

def norm_full(q,uf):
    b={}
    for t in q:b.setdefault(uf.find(t),[]).append(t.pretty())
    return tuple(sorted(tuple(sorted(v)) for v in b.values()))

for k in range(500):
    # Draw 1..10 arbitrary ground equations of axiom depth <=2.
    eqs=[]
    for _ in range(random.randint(1,10)):
        # biased across depths so all thresholds are exercised
        d=random.choice([0,1,1,2,2,2])
        pool=byD[d]
        l=random.choice(pool); r=random.choice(pool)
        eqs.append((l,r))
    red=VisibilityCongruenceClosure(eqs,T1,horizon=2).run()
    for D in range(3):
        pool=byD[D]
        uf,_=close(pool,eqs,ops)
        q=[t for t in T1 if depth(t)<=D]
        assert red.partition(q,D)==norm_full(q,uf),(k,D,eqs)
print({'generic_random_ground_presentations':500,'status':'PASS'})
