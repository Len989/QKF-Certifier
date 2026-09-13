import random,sys
from engine import const,build_pool
from visibility_cc_fast import IncrementalVisibilityCC
from certificates import CertifiedProofStore
random.seed(1776)
ops={'f':1,'g':2};C=[const('a'),const('b')];T1=build_pool(ops,C,1,0);T2=build_pool(ops,C,2,0)
checked=0
for k in range(300):
 eqs=[]
 for _ in range(random.randint(1,12)):
  p=random.choice([C,T1,T2]);eqs.append((random.choice(p),random.choice(p)))
 run=IncrementalVisibilityCC(eqs,T1,horizon=2).run(); store=CertifiedProofStore.from_run(run)
 for _ in range(25):
  s,t=random.sample(T1,2)
  if run.exact_equal(s,t):
   store.validate_goal(s,t)
   assert store.max_level(s,t)==run.first_equal(s,t),(k,s,t,store.max_level(s,t),run.first_equal(s,t))
   checked+=1
print({'certified_random_presentations':300,'equal_queries_checked':checked,'status':'PASS'})
