"""Axiom-support diagnosis for ground visibility proofs.

Given a depth-optimal equality proof, extract the input axioms used by its
certified proof DAG and greedily delete redundant axioms while preserving the
equality at the same (therefore still optimal) proof horizon.

The result is subset-minimal, not minimum-cardinality.  Minimum-cardinality
explanations for congruence closure are NP-hard in general; the greedy routine
is deliberately a diagnostic, not an optimizer.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Sequence, Tuple
from engine import Term
from visibility_cc import AxiomReason, GroundEquation, VisibilityRun
from visibility_cc_fast import IncrementalVisibilityCC
from certificates import CertifiedProofStore

@dataclass
class Diagnosis:
    horizon:int
    initial_support:Tuple[int,...]
    minimal_support:Tuple[int,...]
    equations:Tuple[GroundEquation,...]

    def text(self)->str:
        lines=[f'Optimal horizon D={self.horizon}.',
               f'Certificate support: {len(self.initial_support)} input equations.',
               f'Greedy subset-minimal support: {len(self.minimal_support)} input equations.']
        for i in self.minimal_support:
            e=self.equations[i]
            lines.append(f'  E{i}: {e.left.pretty()} = {e.right.pretty()} [{e.kind}: {e.label}]')
        return '\n'.join(lines)


def _equal_with_indices(eqs:Sequence[GroundEquation],indices:Sequence[int],s:Term,t:Term,D:int)->bool:
    sub=[eqs[i] for i in indices if eqs[i].activation<=D]
    r=IncrementalVisibilityCC(sub,[s,t],horizon=D).run()
    return r.same_at(s,t,D)


def diagnose(run:VisibilityRun,s:Term,t:Term)->Diagnosis:
    D=run.first_equal(s,t)
    if D is None: raise ValueError('target is not equal')
    store=CertifiedProofStore.from_run(run); store.validate_goal(s,t)
    support=[]
    for eid in store.reachable_event_ids(s,t):
        rs=store.certified[eid].event.reason
        if isinstance(rs,AxiomReason):support.append(rs.equation_index)
    support=list(dict.fromkeys(support))
    assert _equal_with_indices(run.equations,support,s,t,D)
    keep=support[:]
    # Deterministic deletion pass; iterate to a fixed point because deleting one
    # equation can make a previously indispensable-looking edge redundant via an alternate proof.
    changed=True
    while changed:
        changed=False
        for i in keep[:]:
            trial=[j for j in keep if j!=i]
            if _equal_with_indices(run.equations,trial,s,t,D):
                keep=trial;changed=True
    # subset minimal check
    assert all(not _equal_with_indices(run.equations,[j for j in keep if j!=i],s,t,D) for i in keep)
    return Diagnosis(D,tuple(support),tuple(keep),tuple(run.equations))

def primitive_support(run:VisibilityRun, indices:Sequence[int])->Tuple[int,...]:
    """Replace explicit TRANSFER bookkeeping rows by their source B-table rows when found.

    The article keeps transferred rows explicitly although they are derivable by
    congruence from D_B.  For user-facing causal diagnosis it is often better to
    report the nonredundant source row instead of treating transfer as an
    independent assumption.  This normalization preserves proof horizon because
    applying alpha(-,a) to a depth-1 operator-table row produces the same depth-2
    consequence.
    """
    out=[]
    for i in indices:
        e=run.equations[i]
        if e.kind=='TRANSFER' and e.left.head==e.right.head and len(e.left.args)==2 and len(e.right.args)==2:
            l0,r0=e.left.args[0],e.right.args[0]
            source=None
            for j,b in enumerate(run.equations):
                if b.kind=='OPERATOR_TABLE' and ((b.left==l0 and b.right==r0) or (b.left==r0 and b.right==l0)):
                    source=j;break
            if source is not None:
                out.append(source);continue
        out.append(i)
    return tuple(dict.fromkeys(out))


def diagnose_primitive(run:VisibilityRun,s:Term,t:Term)->Diagnosis:
    d=diagnose(run,s,t)
    prim=list(primitive_support(run,d.minimal_support))
    # The replacement should remain sufficient at the same horizon; greedily minimize again.
    if not _equal_with_indices(run.equations,prim,s,t,d.horizon):
        return d
    changed=True
    while changed:
        changed=False
        for i in prim[:]:
            trial=[j for j in prim if j!=i]
            if _equal_with_indices(run.equations,trial,s,t,d.horizon):
                prim=trial;changed=True
    return Diagnosis(d.horizon,d.initial_support,tuple(prim),tuple(run.equations))
