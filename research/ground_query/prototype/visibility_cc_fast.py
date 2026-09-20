"""Incremental worklist implementation of visibility-labelled ground congruence closure.

This is an optimized companion to visibility_cc.py.  It activates subterm-DAG
nodes and equations in increasing proof horizon and reprocesses only parent
terms whose argument class can have changed after a union.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .terms import Term, depth
from .visibility_cc import (
    AxiomReason, CongruenceReason, GroundEquation, MergeEvent,
    VisibilityRun, subterms, term_key,
)


class MemberDSU:
    def __init__(self,nodes:Iterable[Term]):
        self.parent={x:x for x in nodes}
        self.size={x:1 for x in nodes}
        self.members={x:{x} for x in nodes}
    def find(self,x:Term)->Term:
        p=self.parent[x]
        if p!=x:
            self.parent[x]=self.find(p)
        return self.parent[x]
    def union(self,a:Term,b:Term):
        ra,rb=self.find(a),self.find(b)
        if ra==rb:return None
        if self.size[ra]<self.size[rb]:ra,rb=rb,ra
        moved=self.members[rb]
        self.parent[rb]=ra;self.size[ra]+=self.size[rb]
        self.members[ra]|=moved
        del self.members[rb]
        return ra,rb,moved


class IncrementalVisibilityCC:
    def __init__(self,equations:Sequence[GroundEquation|Tuple[Term,Term]],queries:Sequence[Term],*,horizon:Optional[int]=None):
        eqs=[]
        for i,e in enumerate(equations):
            if isinstance(e,GroundEquation):eqs.append(e)
            else:eqs.append(GroundEquation(e[0],e[1],label=f'E{i}'))
        self.equations=eqs;self.queries=tuple(dict.fromkeys(queries))
        ns=set()
        for q in self.queries:ns|=subterms(q)
        for e in eqs:ns|=subterms(e.left)|subterms(e.right)
        self.nodes=tuple(sorted(ns,key=term_key))
        natural=max([0]+[depth(x) for x in self.nodes])
        self.horizon=natural if horizon is None else horizon
        if self.horizon<max([0]+[depth(q) for q in self.queries]):raise ValueError('horizon shallower than query')

    def run(self)->VisibilityRun:
        H=self.horizon; nodes=self.nodes;uf=MemberDSU(nodes)
        active:set[Term]=set()
        nodes_by_D:Dict[int,List[Term]]={};eq_by_D:Dict[int,List[int]]={}
        parent_of:Dict[Term,List[Term]]={x:[] for x in nodes}
        for t in nodes:
            d=depth(t)
            if d<=H:nodes_by_D.setdefault(d,[]).append(t)
            for a in t.args:parent_of[a].append(t)
        for i,e in enumerate(self.equations):
            if e.activation<=H:eq_by_D.setdefault(e.activation,[]).append(i)
        proof_adj={x:[] for x in nodes};events=[]
        sig_table:Dict[Tuple[str,Tuple[Term,...]],Term]={}
        current_sig:Dict[Term,Tuple[str,Tuple[Term,...]]]={}
        queue=deque();queued:set[Term]=set()
        stats={'signature_reprocess':0,'queue_push':0,'successful_merges':0,'axiom_activations':0,'signature_collisions':0}

        def enqueue(t:Term):
            if t in active and t.args and t not in queued:
                queue.append(t);queued.add(t);stats['queue_push']+=1

        def merge(a:Term,b:Term,D:int,reason):
            if uf.find(a)==uf.find(b):return False
            res=uf.union(a,b);assert res is not None
            _,_,moved=res
            eid=len(events);ev=MergeEvent(eid,a,b,D,reason);events.append(ev)
            proof_adj[a].append((b,eid));proof_adj[b].append((a,eid))
            stats['successful_merges']+=1
            # Only arguments whose representative changed can change a parent signature.
            for m in sorted(moved, key=term_key):
                for p in parent_of[m]:enqueue(p)
            return True

        def process_term(t:Term,D:int):
            stats['signature_reprocess']+=1
            sig=(t.head,tuple(uf.find(a) for a in t.args))
            old=current_sig.get(t)
            if old is not None and old!=sig and sig_table.get(old)==t:
                del sig_table[old]
            current_sig[t]=sig
            u=sig_table.get(sig)
            if u is not None:
                # Lazy stale-entry guard.
                usig=(u.head,tuple(uf.find(a) for a in u.args))
                if usig!=sig:
                    if sig_table.get(sig)==u:del sig_table[sig]
                    u=None
            if u is None:
                sig_table[sig]=t;return
            if uf.find(u)!=uf.find(t):
                stats['signature_collisions']+=1
                merge(u,t,D,CongruenceReason(t.head,u,t,tuple(zip(u.args,t.args))))

        snapshots={}
        for D in range(H+1):
            # activate terms and immediately index new compound signatures
            for t in nodes_by_D.get(D,[]):
                active.add(t)
                if t.args:enqueue(t)
            # activate each axiom once
            for i in eq_by_D.get(D,[]):
                e=self.equations[i];stats['axiom_activations']+=1
                merge(e.left,e.right,D,AxiomReason(i,e.label,e.kind))
            # saturate congruence consequences
            while queue:
                t=queue.popleft();queued.discard(t)
                process_term(t,D)
            rep_to_id={};snap={};next_id=0;neg=-1
            for t in nodes:
                if t in active:
                    r=uf.find(t)
                    if r not in rep_to_id:rep_to_id[r]=next_id;next_id+=1
                    snap[t]=rep_to_id[r]
                else:snap[t]=neg;neg-=1
            snapshots[D]=snap

        return VisibilityRun(
            equations=self.equations,queries=self.queries,nodes=nodes,horizon=H,
            snapshots=snapshots,merge_events=events,proof_adjacency=proof_adj,
            stats={'nodes':len(nodes),'equations':len(self.equations),'horizon':H,**stats},
            _event_by_id={e.id:e for e in events},
        )
