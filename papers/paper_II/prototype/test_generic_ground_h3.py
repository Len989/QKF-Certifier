import random,sys
from engine import const,build_pool,close,depth
from visibility_cc_fast import IncrementalVisibilityCC
random.seed(20260910)
ops={'f':1,'g':2}; C=[const('a'),const('b')]
T=[build_pool(ops,C,d,0) for d in range(4)]

def norm(q,uf):
 b={}
 for t in q:b.setdefault(uf.find(t),[]).append(t.pretty())
 return tuple(sorted(tuple(sorted(v)) for v in b.values()))
for k in range(120):
 eqs=[]
 for _ in range(random.randint(1,12)):
  d=random.choices([0,1,2,3],weights=[1,2,3,4])[0]
  eqs.append((random.choice(T[d]),random.choice(T[d])))
 # Observe only a sample of depth<=1 terms plus a few random depth2 queries.
 q=list(T[1]) + random.sample(T[2],min(5,len(T[2])))
 run=IncrementalVisibilityCC(eqs,q,horizon=3).run()
 for D in range(4):
  uf,_=close(T[D],eqs,ops)
  qD=[t for t in q if depth(t)<=D]
  assert run.partition(qD,D)==norm(qD,uf),(k,D)
print({'generic_random_ground_h3':120,'T3':len(T[3]),'status':'PASS'})
