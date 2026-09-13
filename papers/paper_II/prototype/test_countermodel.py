import random,sys
from engine import const,build_pool
from visibility_cc_fast import IncrementalVisibilityCC
from countermodel import extract_finite_model,verify_model
random.seed(777);ops={'f':1,'g':2};C=[const('a'),const('b')];T1=build_pool(ops,C,1,0);T2=build_pool(ops,C,2,0)
for k in range(200):
 eqs=[]
 for _ in range(random.randint(0,10)):
  p=random.choice([C,T1,T2]);eqs.append((random.choice(p),random.choice(p)))
 r=IncrementalVisibilityCC(eqs,T1,horizon=2).run();m=extract_finite_model(r);verify_model(r,m)
print({'countermodels_random_ground':200,'status':'PASS'})
