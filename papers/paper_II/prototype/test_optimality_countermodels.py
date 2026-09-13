import random,sys
from engine import const,build_pool,depth
from visibility_cc_fast import IncrementalVisibilityCC
from countermodel import extract_finite_model,verify_model
random.seed(4444);ops={'f':1,'g':2};C=[const('a'),const('b')];T1=build_pool(ops,C,1,0);T2=build_pool(ops,C,2,0)
late=0;neq=0
for k in range(300):
 eqs=[]
 for _ in range(random.randint(1,10)):
  p=random.choice([C,T1,T2]);eqs.append((random.choice(p),random.choice(p)))
 r=IncrementalVisibilityCC(eqs,T1,horizon=2).run()
 # final model separates all final classes
 mf=extract_finite_model(r,2);verify_model(r,mf,2)
 for _ in range(20):
  s,t=random.sample(T1,2);D=r.first_equal(s,t)
  if D is None:
   assert mf.eval(s)!=mf.eval(t);neq+=1
  else:
   d=max(depth(s),depth(t))
   if D>d:
    ml=extract_finite_model(r,D-1);verify_model(r,ml,D-1)
    assert ml.eval(s)!=ml.eval(t);late+=1
print({'late_equalities_with_lower_countermodel':late,'final_nonequalities_separated':neq,'status':'PASS'})
