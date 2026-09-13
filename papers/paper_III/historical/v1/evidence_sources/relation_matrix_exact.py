from __future__ import annotations
from collections import defaultdict
from itertools import product
from typing import Dict,Tuple,Set,List

Copy=Tuple[str,int] | Tuple[str]
CENTRAL=('C',)

def flat(args,n):
 z=0
 for a in args:z=z*n+a
 return z

class RelationMatrixExact:
    """Explicit oracle for the relation-matrix formulation of the slice amalgam.

    This intentionally enumerates relations; it is not the scalable algorithm.
    It validates the algebraic fixed-point that the symbolic/Horn backend will use.
    Binary transformer; native operations must have positive arity.
    """
    def __init__(self,n:int,ops:List[Tuple[int,List[int]]],observations):
        if type(n) is not int or n < 1: raise ValueError("nonempty finite carrier required")
        if any(ar < 1 or len(tab) != n**ar or any(v not in range(n) for v in tab) for ar, tab in ops):
            raise ValueError("positive arity and a complete carrier-valued table required")
        self.n=n;self.ops=ops
        self.copies=[CENTRAL]+[('R',b) for b in range(n)]+[('K',a) for a in range(n)]
        self.R:Dict[Tuple[Copy,Copy],Set[Tuple[int,int]]]=defaultdict(set)
        # Reflexivity within every full copy.
        for c in self.copies:
            self.R[c,c].update((a,a) for a in range(n))
        # Every tensor cell has row and column views.
        for a in range(n):
            for b in range(n):
                self._add(('R',b),('K',a),a,b)
        # Observations glue the physical cell to central carrier.
        for xs,y in observations:
            a,b=xs
            self._add(('R',b),CENTRAL,a,y)
            self._add(('K',a),CENTRAL,b,y)
    def _add(self,s,t,a,b):
        ch=(a,b) not in self.R[s,t]
        self.R[s,t].add((a,b)); self.R[t,s].add((b,a))
        return ch
    def _op(self,opidx,args):
        ar,tab=self.ops[opidx]
        return tab[flat(args,self.n)]
    def compatibility(self)->bool:
        changed=False
        for key,S in list(self.R.items()):
            if not S:continue
            cur=list(S)
            for oi,(ar,tab) in enumerate(self.ops):
                if ar==0:
                    p=(tab[0],tab[0])
                    if p not in S:S.add(p);changed=True
                else:
                    # Exact but intentionally small-ground only.
                    for tup in product(cur,repeat=ar):
                        a=self._op(oi,tuple(p[0] for p in tup))
                        b=self._op(oi,tuple(p[1] for p in tup))
                        if (a,b) not in S:S.add((a,b));changed=True
            # symmetry may receive new pairs
            s,t=key
            for a,b in list(S):
                if (b,a) not in self.R[t,s]:self.R[t,s].add((b,a));changed=True
        return changed
    def transitivity(self)->bool:
        changed=False
        # Build outgoing neighbor maps from currently nonempty relations.
        outs=defaultdict(list)
        for (s,t),rel in self.R.items():
            if rel:outs[s].append(t)
        additions=[]
        for s,js in list(outs.items()):
            for j in js:
                A=self.R[s,j]
                if not A:continue
                by_mid=defaultdict(list)
                for a,b in A:by_mid[b].append(a)
                for t in outs.get(j,[]):
                    B=self.R[j,t]
                    if not B:continue
                    for b,c in B:
                        for a in by_mid.get(b,()):
                            if (a,c) not in self.R[s,t]:additions.append((s,t,a,c))
        for s,t,a,c in additions:
            if self._add(s,t,a,c):changed=True
        return changed

    def quotient_feedback(self)->bool:
        """Lift central carrier congruence into slice local coordinates and contexts."""
        changed=False
        th=list(self.R[CENTRAL,CENTRAL])
        # Local coordinate: equal carrier inputs denote equal local elements in every copy.
        for a,c in th:
            for cp in self.copies:
                if self._add(cp,cp,a,c):changed=True
        # Context coordinate: theta-equivalent fixed arguments identify whole slice copies pointwise.
        for b,d in th:
            for x in range(self.n):
                if self._add(('R',b),('R',d),x,x):changed=True
                if self._add(('K',b),('K',d),x,x):changed=True
        return changed

    def solve(self,max_rounds=None):
        rd = 0
        while max_rounds is None or rd < max_rounds:
            rd += 1
            ch=False
            if self.quotient_feedback():ch=True
            if self.compatibility():ch=True
            if self.transitivity():ch=True
            if not ch:return rd
        raise RuntimeError('no convergence')
    def carrier_blocks(self):
        rel=self.R[CENTRAL,CENTRAL]
        seen=set();blocks=[]
        for a in range(self.n):
            if a in seen:continue
            b={x for x in range(self.n) if (a,x) in rel}
            seen|=b;blocks.append(sorted(b))
        return blocks
    def known(self):
        out={}
        for a in range(self.n):
            for b in range(self.n):
                ys={y for x,y in self.R[('R',b),CENTRAL] if x==a}
                if ys:out[(a,b)]=ys
        return out
