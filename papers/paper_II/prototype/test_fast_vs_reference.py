import random,sys
from engine import const,build_pool
from visibility_cc import VisibilityCongruenceClosure
from visibility_cc_fast import IncrementalVisibilityCC
random.seed(112233)
ops={'f':1,'g':2};C=[const('a'),const('b')];T1=build_pool(ops,C,1,0);T2=build_pool(ops,C,2,0)
for k in range(1000):
 eqs=[]
 for _ in range(random.randint(0,12)):
  p=random.choice([C,T1,T2]);eqs.append((random.choice(p),random.choice(p)))
 a=VisibilityCongruenceClosure(eqs,T1,horizon=2).run();b=IncrementalVisibilityCC(eqs,T1,horizon=2).run()
 for D in range(3):
  assert a.partition([t for t in T1 if (0 if not t.args else 1)<=D],D)==b.partition([t for t in T1 if (0 if not t.args else 1)<=D],D),(k,D)
 for i,s in enumerate(T1):
  for t in T1[i:]:assert a.first_equal(s,t)==b.first_equal(s,t),(k,s,t,a.first_equal(s,t),b.first_equal(s,t))
print({'fast_vs_reference_random':1000,'status':'PASS'})
