import random,sys
from engine import const,build_pool
from visibility_cc_fast import IncrementalVisibilityCC
random.seed(621);ops={'f':1,'g':2};C=[const('a'),const('b')];T1=build_pool(ops,C,1,0);T2=build_pool(ops,C,2,0)
def forest_stab(run,Q):
 Q=list(Q);D=max([0]+[0 if not t.args else 1 for t in Q]);snap=run.snapshots[run.horizon]
 blocks={}
 for q in Q:blocks.setdefault(snap[q],[]).append(q)
 for qs in blocks.values():
  b=qs[0]
  for q in qs[1:]:D=max(D,run.proof_bottleneck(b,q))
 return D
for k in range(500):
 eqs=[]
 for _ in range(random.randint(0,10)):
  p=random.choice([C,T1,T2]);eqs.append((random.choice(p),random.choice(p)))
 r=IncrementalVisibilityCC(eqs,T1,horizon=2).run()
 assert forest_stab(r,C)==r.stabilization_horizon(C)
 assert forest_stab(r,T1)==r.stabilization_horizon(T1)
print({'forest_stabilization_random':500,'status':'PASS'})
