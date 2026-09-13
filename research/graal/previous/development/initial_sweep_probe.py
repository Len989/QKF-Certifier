from collections import deque
from itertools import product

def cmp(a,b):return (a>b)-(a<b)
def lead(a,b,suffix):return cmp(a,b) or suffix
def forward(prefix,a,b):return prefix or cmp(a,b)

ALPHABET=[(a,o,u,x,y) for a,o in [(0,0),(0,1),(1,0)] for u in [0,1]
          for x in range(a,a+o+1) for y in range(a,a+o+1)]
START=(7,0,0,0,0)

def step(state,col,weak=False):
    P,au,xu,yu,xy=state;a,o,u,x,y=col
    new=0
    for h in [-1,0,1]:
        lower_ok=bool(P&(1<<(forward(h,y,u)+1)))
        chosen=(forward(h,1,u) or au)<=0
        if lower_ok and (not o or y==chosen):new|=1<<(h+1)
    return (7 if weak else new,lead(a,u,au),lead(x,u,xu),lead(y,u,yu),lead(x,y,xy))

def finish(state,a,u):
    P,au,xu,yu,xy=state;h=cmp(1-a,1-u)
    return bool(P&(1<<(h+1))) and lead(1-a,1-u,xu)<=0 and (lead(1-a,1-u,yu)>0 or xy>0)

def run(weak=False):
    parents={START:None};queue=deque([START]);bad=None
    while queue:
        q=queue.popleft()
        for a,u in product(range(2),repeat=2):
            if finish(q,a,u):bad=(q,a,u);break
        if bad:break
        for col in ALPHABET:
            r=step(q,col,weak)
            if r not in parents:parents[r]=(q,col);queue.append(r)
    if bad:
        q,a,u=bad;columns=[]
        while parents[q] is not None:
            q,col=parents[q];columns.append(col)
        columns.reverse();columns.append((a,0,u,a,a))
        words=[sum(c[i]<<j for j,c in enumerate(columns)) for i in range(5)]
        return dict(status='counterexample',states=len(parents),width=len(columns),words=dict(zip(['base','optional','bound','candidate','output'],words)))
    return dict(status='passed',states=len(parents),transitions=len(parents)*len(ALPHABET),sign_checks=len(parents)*4)

if __name__=='__main__':
    import json
    print(json.dumps(dict(full=run(),weakened=run(True))))
