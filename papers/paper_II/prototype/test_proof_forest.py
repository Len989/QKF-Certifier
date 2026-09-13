import random,sys,itertools
from engine import const,build_pool,close,depth
from visibility_cc import VisibilityCongruenceClosure
random.seed(9898)
ops={'f':1,'g':2};C=[const('a'),const('b')]
T1=build_pool(ops,C,1,0);T2=build_pool(ops,C,2,0)
for k in range(120):
 eqs=[]
 for _ in range(random.randint(1,10)):
  p=random.choice([C,T1,T2]); eqs.append((random.choice(p),random.choice(p)))
 run=VisibilityCongruenceClosure(eqs,T1,horizon=2).run()
 for i,s in enumerate(T1):
  for t in T1[i:]:
   f=run.first_equal(s,t);b=run.proof_bottleneck(s,t)
   if f!=b:
    print('FAIL',k,s.pretty(),t.pretty(),f,b);raise SystemExit(1)
print({'random_presentations':120,'all_query_pair_bottlenecks':'PASS'})
