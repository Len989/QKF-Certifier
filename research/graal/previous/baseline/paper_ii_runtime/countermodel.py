"""Finite countermodel extraction from a completed ground congruence run.

For finite ground E and a finite query set Q, the final congruence classes of
S = Sub(E) union Sub(Q) form a finite partial term algebra.  Completing each
undefined operation tuple with an arbitrary default class gives a total finite
model of E.  Every S-node evaluates to its congruence class, so inequivalent
query terms are separated simultaneously.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict,Iterable,List,Tuple
from engine import Term
from visibility_cc import VisibilityRun

@dataclass
class FiniteGroundModel:
    domain: Tuple[int,...]
    constants: Dict[str,int]
    operations: Dict[str,Dict[Tuple[int,...],int]]
    arities: Dict[str,int]
    default: int

    def eval(self,t:Term)->int:
        if not t.args:
            return self.constants.get(t.head,self.default)
        vals=tuple(self.eval(a) for a in t.args)
        return self.operations.get(t.head,{}).get(vals,self.default)


def extract_finite_model(run:VisibilityRun, D:int|None=None)->FiniteGroundModel:
    if D is None: D=run.horizon
    if D not in run.snapshots: raise ValueError(f"no snapshot at horizon {D}")
    snap=run.snapshots[D]
    active_nodes=[t for t in run.nodes if __import__("engine").depth(t)<=D]
    classes=sorted(set(snap[t] for t in active_nodes if snap[t]>=0))
    remap={c:i for i,c in enumerate(classes)}
    if not classes:
        classes=[0];remap={0:0}
    default=0
    constants={}
    operations:Dict[str,Dict[Tuple[int,...],int]]={};arities={}
    for t in active_nodes:
        if not t.args:
            constants[t.head]=remap[snap[t]]
        else:
            arities.setdefault(t.head,len(t.args))
            if arities[t.head]!=len(t.args):raise ValueError('inconsistent arity')
            key=tuple(remap[snap[a]] for a in t.args);val=remap[snap[t]]
            old=operations.setdefault(t.head,{}).get(key)
            if old is not None and old!=val:
                raise AssertionError('congruence closure did not make operation well-defined')
            operations[t.head][key]=val
    return FiniteGroundModel(tuple(range(len(classes))),constants,operations,arities,default)


def verify_model(run:VisibilityRun,model:FiniteGroundModel,D:int|None=None)->None:
    if D is None: D=run.horizon
    active_nodes=[t for t in run.nodes if __import__("engine").depth(t)<=D]
    for i,e in enumerate(run.equations):
        if e.activation<=D and model.eval(e.left)!=model.eval(e.right):
            raise AssertionError(f'model violates equation {i}: {e.left.pretty()}={e.right.pretty()}')
    # Stronger invariant: every DAG node evaluates to its final congruence class up to renaming.
    # We test pairwise equality rather than depending on the internal remap.
    for i,s in enumerate(active_nodes):
        for t in active_nodes[i+1:]:
            same=run.same_at(s,t,D)
            if (model.eval(s)==model.eval(t))!=same:
                raise AssertionError(f'model does not exactly separate DAG classes: {s.pretty()}, {t.pretty()}')
