"""Visibility-labelled congruence closure on a finite ground subterm DAG.

Research prototype based on the equality-visibility framework of the paper.
It deliberately does *not* enumerate the full term universe T^(D).  For a
finite ground equation set E and finite query set Q it works on

    S = Sub(E) union Sub(Q)

and processes proof horizons D in increasing order.  At each horizon it
computes ordinary ground congruence closure on the active nodes/equations.
The first horizon at which two query terms are connected is their pairwise
visibility depth lambda_E(s,t).

The implementation below is a deliberately transparent reference version.
It rescans active terms after merges instead of implementing the near-linear
Downey-Sethi-Tarjan/Nelson-Oppen worklist machinery.  This makes it suitable
for auditing the mathematics and producing proof provenance.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from engine import Term, depth


@dataclass(frozen=True)
class GroundEquation:
    left: Term
    right: Term
    label: str = "axiom"
    kind: str = "AXIOM"

    @property
    def activation(self) -> int:
        return max(depth(self.left), depth(self.right))


@dataclass(frozen=True)
class AxiomReason:
    equation_index: int
    label: str
    kind: str


@dataclass(frozen=True)
class CongruenceReason:
    head: str
    left: Term
    right: Term
    argument_pairs: Tuple[Tuple[Term, Term], ...]


Reason = AxiomReason | CongruenceReason


@dataclass(frozen=True)
class MergeEvent:
    id: int
    left: Term
    right: Term
    level: int
    reason: Reason


class DSU:
    def __init__(self, nodes: Iterable[Term]):
        self.parent: Dict[Term, Term] = {x: x for x in nodes}
        self.size: Dict[Term, int] = {x: 1 for x in nodes}

    def find(self, x: Term) -> Term:
        p = self.parent[x]
        if p != x:
            self.parent[x] = self.find(p)
        return self.parent[x]

    def union(self, a: Term, b: Term) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]
        return True


def subterms(t: Term) -> Set[Term]:
    out: Set[Term] = set()
    stack = [t]
    while stack:
        u = stack.pop()
        if u in out:
            continue
        out.add(u)
        stack.extend(u.args)
    return out


def term_key(t: Term) -> Tuple[int, str]:
    return depth(t), t.pretty()


@dataclass
class VisibilityRun:
    equations: List[GroundEquation]
    queries: Tuple[Term, ...]
    nodes: Tuple[Term, ...]
    horizon: int
    snapshots: Dict[int, Dict[Term, int]]
    merge_events: List[MergeEvent]
    proof_adjacency: Dict[Term, List[Tuple[Term, int]]]
    stats: Dict[str, int | float]
    _event_by_id: Dict[int, MergeEvent] = field(repr=False)

    def same_at(self, s: Term, t: Term, D: int) -> bool:
        if D not in self.snapshots:
            raise ValueError(f"no snapshot for horizon {D}")
        snap = self.snapshots[D]
        return snap[s] == snap[t]

    def first_equal(self, s: Term, t: Term) -> Optional[int]:
        start = max(depth(s), depth(t))
        for D in range(start, self.horizon + 1):
            if self.same_at(s, t, D):
                return D
        return None

    def exact_equal(self, s: Term, t: Term) -> bool:
        return self.same_at(s, t, self.horizon)

    def partition(self, terms: Iterable[Term], D: int) -> Tuple[Tuple[str, ...], ...]:
        snap = self.snapshots[D]
        blocks: Dict[int, List[str]] = {}
        for t in terms:
            blocks.setdefault(snap[t], []).append(t.pretty())
        norm = [tuple(sorted(v)) for v in blocks.values()]
        return tuple(sorted(norm))

    def stabilization_horizon(self, terms: Iterable[Term]) -> int:
        """Least D at which the relation on `terms` equals the final relation.

        All terms must have depth <= D at the candidate horizon.  The search
        starts at the maximum term depth.
        """
        ts = tuple(terms)
        if not ts:
            return 0
        start = max(depth(t) for t in ts)
        target = self.partition(ts, self.horizon)
        for D in range(start, self.horizon + 1):
            if self.partition(ts, D) == target:
                return D
        raise AssertionError("final horizon did not stabilize its own partition")

    def proof_path(self, s: Term, t: Term) -> List[MergeEvent]:
        """Return the unique forest path connecting s,t in the successful-union forest."""
        if not self.exact_equal(s, t):
            return []
        if s == t:
            return []
        prev: Dict[Term, Tuple[Optional[Term], Optional[int]]] = {s: (None, None)}
        q = deque([s])
        while q:
            u = q.popleft()
            if u == t:
                break
            for v, event_id in self.proof_adjacency.get(u, ()):
                if v not in prev:
                    prev[v] = (u, event_id)
                    q.append(v)
        if t not in prev:
            raise AssertionError("DSU says equal but proof forest has no path")
        ids: List[int] = []
        cur = t
        while prev[cur][0] is not None:
            p, eid = prev[cur]
            assert p is not None and eid is not None
            ids.append(eid)
            cur = p
        ids.reverse()
        return [self._event_by_id[i] for i in ids]

    def proof_bottleneck(self, s: Term, t: Term) -> Optional[int]:
        if not self.exact_equal(s, t):
            return None
        path = self.proof_path(s, t)
        return max([max(depth(s), depth(t))] + [e.level for e in path])

    def explain_text(self, s: Term, t: Term, *, recursive: bool = True, max_lines: int = 200) -> str:
        """Return an acyclic, depth-optimal proof certificate.

        Earlier research versions recursively expanded argument equalities using
        paths in the *final* union forest.  Although the forest correctly
        records equality and bottleneck levels, that presentation can be
        self-referential: a final path for a congruence premise may pass through
        the parent equality currently being explained.  Certified proof
        extraction must instead freeze premise paths at the instant of each
        congruence merge.  The certificates module performs that chronological
        replay and is now the authoritative explanation mechanism.
        """
        from certificates import CertifiedProofStore
        return CertifiedProofStore.from_run(self).explain_text(s, t, max_lines=max_lines)



class VisibilityCongruenceClosure:
    """Reference threshold congruence-closure algorithm."""

    def __init__(
        self,
        equations: Sequence[GroundEquation | Tuple[Term, Term]],
        queries: Sequence[Term],
        *,
        horizon: Optional[int] = None,
    ):
        eqs: List[GroundEquation] = []
        for i, e in enumerate(equations):
            if isinstance(e, GroundEquation):
                eqs.append(e)
            else:
                l, r = e
                eqs.append(GroundEquation(l, r, label=f"E{i}"))
        self.equations = eqs
        self.queries = tuple(dict.fromkeys(queries))
        nodes: Set[Term] = set(self.queries)
        for q in self.queries:
            nodes |= subterms(q)
        for e in eqs:
            nodes |= subterms(e.left)
            nodes |= subterms(e.right)
        self.nodes = tuple(sorted(nodes, key=term_key))
        natural_H = max([0] + [depth(t) for t in self.nodes])
        if horizon is None:
            horizon = natural_H
        if horizon < max([0] + [depth(q) for q in self.queries]):
            raise ValueError("horizon is shallower than a query term")
        if horizon < max([0] + [e.activation for e in eqs]):
            # A smaller bounded run is legitimate, but it is not an exact full-ground run.
            # We allow it; callers should know the difference.
            pass
        self.horizon = horizon

    def run(self) -> VisibilityRun:
        nodes = self.nodes
        H = self.horizon
        uf = DSU(nodes)
        active: Set[Term] = set()
        active_eqs: List[int] = []
        eqs_by_D: Dict[int, List[int]] = {}
        nodes_by_D: Dict[int, List[Term]] = {}
        for t in nodes:
            if depth(t) <= H:
                nodes_by_D.setdefault(depth(t), []).append(t)
        for i, e in enumerate(self.equations):
            if e.activation <= H:
                eqs_by_D.setdefault(e.activation, []).append(i)

        proof_adj: Dict[Term, List[Tuple[Term, int]]] = {t: [] for t in nodes}
        events: List[MergeEvent] = []
        scans = 0
        congruence_attempts = 0
        axiom_attempts = 0

        def merge(a: Term, b: Term, D: int, reason: Reason) -> bool:
            if a not in active or b not in active:
                raise AssertionError("attempted merge of inactive term")
            if uf.find(a) == uf.find(b):
                return False
            ok = uf.union(a, b)
            assert ok
            eid = len(events)
            ev = MergeEvent(eid, a, b, D, reason)
            events.append(ev)
            proof_adj[a].append((b, eid))
            proof_adj[b].append((a, eid))
            return True

        snapshots: Dict[int, Dict[Term, int]] = {}
        # Block ids in snapshots are canonicalized integers, independent of DSU representatives.
        for D in range(H + 1):
            for t in nodes_by_D.get(D, ()):
                active.add(t)
            active_eqs.extend(eqs_by_D.get(D, ()))

            changed = True
            while changed:
                changed = False
                scans += 1
                for i in active_eqs:
                    e = self.equations[i]
                    if e.left not in active or e.right not in active:
                        continue
                    axiom_attempts += 1
                    if merge(
                        e.left,
                        e.right,
                        D,
                        AxiomReason(i, e.label, e.kind),
                    ):
                        changed = True

                # Congruence on the induced partial term algebra S_{<=D}.
                buckets: Dict[Tuple[str, Tuple[Term, ...]], Term] = {}
                for t in active:
                    if not t.args:
                        continue
                    sig = (t.head, tuple(uf.find(a) for a in t.args))
                    u = buckets.get(sig)
                    if u is None:
                        buckets[sig] = t
                    else:
                        congruence_attempts += 1
                        if uf.find(u) != uf.find(t):
                            reason = CongruenceReason(
                                head=t.head,
                                left=u,
                                right=t,
                                argument_pairs=tuple(zip(u.args, t.args)),
                            )
                            if merge(u, t, D, reason):
                                changed = True

            # Store exact active partition at this threshold. Inactive nodes get unique negative ids
            # so callers cannot accidentally read them as equal before they exist.
            rep_to_id: Dict[Term, int] = {}
            snap: Dict[Term, int] = {}
            next_id = 0
            next_inactive = -1
            for t in nodes:
                if t in active:
                    r = uf.find(t)
                    if r not in rep_to_id:
                        rep_to_id[r] = next_id
                        next_id += 1
                    snap[t] = rep_to_id[r]
                else:
                    snap[t] = next_inactive
                    next_inactive -= 1
            snapshots[D] = snap

        event_by_id = {e.id: e for e in events}
        return VisibilityRun(
            equations=self.equations,
            queries=self.queries,
            nodes=nodes,
            horizon=H,
            snapshots=snapshots,
            merge_events=events,
            proof_adjacency=proof_adj,
            stats={
                "nodes": len(nodes),
                "equations": len(self.equations),
                "horizon": H,
                "successful_merges": len(events),
                "saturation_scans": scans,
                "axiom_attempts": axiom_attempts,
                "congruence_attempts": congruence_attempts,
            },
            _event_by_id=event_by_id,
        )


def labelled_equations(
    eqs: Sequence[Tuple[Term, Term]],
    labels: Optional[Sequence[str]] = None,
    kinds: Optional[Sequence[str]] = None,
) -> List[GroundEquation]:
    out = []
    for i, (l, r) in enumerate(eqs):
        label = labels[i] if labels is not None else f"E{i}"
        kind = kinds[i] if kinds is not None else "AXIOM"
        out.append(GroundEquation(l, r, label=label, kind=kind))
    return out

# --- Optional explanation refinement -------------------------------------------------

def _shortest_top_level_path(run: VisibilityRun, s: Term, t: Term, D: int):
    """Heuristic shortest proof path at a fixed, already-correct threshold.

    The graph contains every admitted axiom edge and every congruence edge
    between active subterm-DAG nodes whose argument tuples are already equal at
    horizon D.  This is intended for readable explanations, not as a theorem
    about minimum proof size.
    """
    active=[u for u in run.nodes if depth(u)<=D]
    adj: Dict[Term,List[Tuple[Term,Reason]]] = {u:[] for u in active}
    for i,e in enumerate(run.equations):
        if e.activation<=D and e.left in adj and e.right in adj:
            rs=AxiomReason(i,e.label,e.kind)
            adj[e.left].append((e.right,rs));adj[e.right].append((e.left,rs))
    by_head: Dict[str,List[Term]]={}
    for u in active:
        if u.args: by_head.setdefault(u.head,[]).append(u)
    snap=run.snapshots[D]
    for head,ts in by_head.items():
        buckets: Dict[Tuple[int,...],List[Term]]={}
        for u in ts:
            sig=tuple(snap[a] for a in u.args)
            buckets.setdefault(sig,[]).append(u)
        for group in buckets.values():
            for i,u in enumerate(group):
                for v in group[i+1:]:
                    rs=CongruenceReason(head,u,v,tuple(zip(u.args,v.args)))
                    adj[u].append((v,rs));adj[v].append((u,rs))
    # Dijkstra with a mild preference for semantic axiom edges over congruence edges.
    # Primary objective: number of top-level steps. Secondary: fewer congruence premises.
    import heapq
    dist={s:(0,0)}; prev={}
    heap=[(0,0,0,s)]; serial=0
    while heap:
        steps,pen,_,u=heapq.heappop(heap)
        if dist.get(u)!=(steps,pen):continue
        if u==t:break
        for v,rs in adj[u]:
            addpen=0 if isinstance(rs,AxiomReason) else sum(1 for a,b in rs.argument_pairs if a!=b)
            nd=(steps+1,pen+addpen)
            if v not in dist or nd<dist[v]:
                dist[v]=nd;prev[v]=(u,rs);serial+=1;heapq.heappush(heap,(nd[0],nd[1],serial,v))
    if t not in dist:return []
    path=[];cur=t
    while cur!=s:
        u,rs=prev[cur];path.append((u,cur,rs));cur=u
    path.reverse();return path


def short_explanation_text(run: VisibilityRun, s: Term, t: Term, *, max_lines: int=200) -> str:
    """Compatibility wrapper for the certified explanation mechanism."""
    from certificates import CertifiedProofStore
    return CertifiedProofStore.from_run(run).explain_text(s,t,max_lines=max_lines)
