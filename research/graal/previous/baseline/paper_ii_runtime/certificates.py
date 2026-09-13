"""Certified proof/explanation extraction for visibility-labelled ground congruence closure.

Why this module exists
----------------------
A successful-union forest is enough to recover *that* two nodes are equal and
the maximum horizon on the unique union path.  It is not, by itself, enough to
print a logically valid recursive congruence proof: a later forest path chosen
for an argument equality can pass through the very parent equality being
explained and create a circular-looking certificate.

The fix is to replay merge events in chronological order.  At the instant a
congruence merge is performed, each corresponding argument pair is already
connected by earlier merge events.  We freeze those earlier forest paths as the
premises of the congruence event.  Event ids therefore strictly decrease under
recursive expansion, giving an acyclic proof DAG.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from engine import Term, depth
from visibility_cc import AxiomReason, CongruenceReason, MergeEvent, VisibilityRun


@dataclass(frozen=True)
class CertifiedEvent:
    event: MergeEvent
    # One event-id path for every nontrivial argument equality of a congruence event.
    premise_paths: Tuple[Tuple[int, ...], ...] = ()
    premise_pairs: Tuple[Tuple[Term, Term], ...] = ()


class _Forest:
    def __init__(self, nodes: Iterable[Term]):
        self.adj: Dict[Term, List[Tuple[Term, int]]] = {x: [] for x in nodes}

    def add(self, a: Term, b: Term, eid: int) -> None:
        self.adj[a].append((b, eid)); self.adj[b].append((a, eid))

    def path_ids(self, s: Term, t: Term) -> Optional[Tuple[int, ...]]:
        if s == t:
            return ()
        prev: Dict[Term, Tuple[Optional[Term], Optional[int]]] = {s:(None,None)}
        q=deque([s])
        while q:
            u=q.popleft()
            if u==t: break
            for v,eid in self.adj[u]:
                if v not in prev:
                    prev[v]=(u,eid);q.append(v)
        if t not in prev:
            return None
        ids=[];cur=t
        while prev[cur][0] is not None:
            p,eid=prev[cur]; assert p is not None and eid is not None
            ids.append(eid);cur=p
        ids.reverse();return tuple(ids)


@dataclass
class CertifiedProofStore:
    run: VisibilityRun
    certified: Dict[int, CertifiedEvent]
    final_forest: _Forest

    @classmethod
    def from_run(cls, run: VisibilityRun) -> 'CertifiedProofStore':
        forest=_Forest(run.nodes)
        cert: Dict[int,CertifiedEvent]={}
        for ev in run.merge_events:
            paths=[];pairs=[]
            if isinstance(ev.reason,CongruenceReason):
                # Premises must already be justified before this successful union.
                if ev.reason.left.head != ev.reason.right.head:
                    raise AssertionError('congruence event has different heads')
                if len(ev.reason.left.args)!=len(ev.reason.right.args):
                    raise AssertionError('congruence event has different arities')
                for x,y in ev.reason.argument_pairs:
                    if x==y: continue
                    p=forest.path_ids(x,y)
                    if p is None:
                        raise AssertionError(
                            f'event {ev.id} used unproved congruence premise {x.pretty()}={y.pretty()}'
                        )
                    if any(i>=ev.id for i in p):
                        raise AssertionError('premise path is not chronologically earlier')
                    paths.append(p);pairs.append((x,y))
            elif not isinstance(ev.reason,AxiomReason):
                raise AssertionError('unknown merge reason')
            cert[ev.id]=CertifiedEvent(ev,tuple(paths),tuple(pairs))
            forest.add(ev.left,ev.right,ev.id)
        return cls(run,cert,forest)

    def top_path(self,s:Term,t:Term)->Tuple[int,...]:
        p=self.final_forest.path_ids(s,t)
        if p is None:
            return ()
        return p

    def event_dependencies(self,eid:int)->Tuple[int,...]:
        ce=self.certified[eid]
        deps=[]
        for p in ce.premise_paths: deps.extend(p)
        # preserve order while removing duplicates
        return tuple(dict.fromkeys(deps))

    def reachable_event_ids(self,s:Term,t:Term)->Tuple[int,...]:
        roots=list(self.top_path(s,t)); seen=set();out=[]
        def visit(eid:int):
            if eid in seen:return
            seen.add(eid)
            for d in self.event_dependencies(eid):visit(d)
            out.append(eid)
        for r in roots:visit(r)
        return tuple(out)  # topological: dependencies first

    def validate_goal(self,s:Term,t:Term)->None:
        if s==t:return
        if not self.run.exact_equal(s,t):
            raise ValueError('goal is not equal in final ground closure')
        ids=self.reachable_event_ids(s,t)
        established=_Forest(self.run.nodes)
        for eid in ids:
            ce=self.certified[eid];ev=ce.event
            if isinstance(ev.reason,CongruenceReason):
                for (x,y),p in zip(ce.premise_pairs,ce.premise_paths):
                    # All events in the frozen premise path must have been established already.
                    if any(i not in ids for i in p):raise AssertionError('missing dependency')
                    if established.path_ids(x,y) is None:
                        raise AssertionError(f'premise not established before event {eid}')
            established.add(ev.left,ev.right,eid)
        if established.path_ids(s,t) is None:
            raise AssertionError('certificate does not establish goal')

    def max_level(self,s:Term,t:Term)->Optional[int]:
        if not self.run.exact_equal(s,t):return None
        ids=self.reachable_event_ids(s,t)
        return max([max(depth(s),depth(t))]+[self.certified[i].event.level for i in ids])

    def explain_text(self,s:Term,t:Term,max_lines:int=300)->str:
        D=self.run.first_equal(s,t)
        if D is None:
            return f'No equality at exact horizon {self.run.horizon}: {s.pretty()} != {t.pretty()}.'
        self.validate_goal(s,t)
        lines=[f'Goal: {s.pretty()} = {t.pretty()}',f'Optimal proof horizon: D={D}.']
        printed=set()
        def emit_event(eid:int,indent:int=0):
            if len(lines)>=max_lines:return
            if eid in printed:
                lines.append(' '*indent+f'(reuse event {eid})');return
            ce=self.certified[eid];ev=ce.event
            # Premises first yields a genuine acyclic derivation DAG.
            if isinstance(ev.reason,CongruenceReason):
                for p in ce.premise_paths:
                    for dep in p:emit_event(dep,indent+2)
            reason=ev.reason
            if isinstance(reason,AxiomReason):
                msg=f'event {eid}, D={ev.level}: {ev.left.pretty()} = {ev.right.pretty()} by {reason.kind} [{reason.label}]'
            else:
                msg=f'event {eid}, D={ev.level}: {ev.left.pretty()} = {ev.right.pretty()} by congruence under {reason.head}'
            lines.append(' '*indent+msg);printed.add(eid)
        for eid in self.top_path(s,t):emit_event(eid,0)
        if len(lines)>=max_lines:lines.append('... certificate truncated ...')
        return '\n'.join(lines)
