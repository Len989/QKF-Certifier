"""Exact low-depth visibility profiles for the finite ground action theories.

For the published theories h(E) <= 2.  The ground-locality theorem in the
article says that closure at horizon h(E) is exact on every lower layer.
This module compares restricted partitions at horizons 0,1,...,h(E) and
therefore computes delta_E(d) for d < h(E) without assuming that class-count
plateaux imply exactness.
"""
from __future__ import annotations

from typing import Dict, Iterable, Sequence

from algebras import Algebra
from engine import Result, Term, synthesize


def _partition(terms: Iterable[Term], result: Result):
    if result.uf is None:
        raise ValueError("result has no union-find state")
    blocks = {}
    for t in terms:
        blocks.setdefault(result.uf.find(t), set()).add(t)
    return frozenset(frozenset(block) for block in blocks.values())


def visibility_profile(
    A: Algebra,
    B: Algebra,
    *,
    ident: str = "none",
    schemes: Sequence[str] = (),
    merge: bool = False,
    merge_op: str | None = None,
    tab=None,
    h: int = 2,
) -> Dict[str, object]:
    """Compute delta_E(d), omega_E(d)=delta_E(d)-d for 0 <= d < h.

    Correctness uses the article's ground-locality theorem: the partition
    induced by proof horizon h is the full equality relation on each target
    layer d<h, provided h is at least the axiom depth of the theory.
    """
    if h < 0:
        raise ValueError("h must be nonnegative")
    results = {
        D: synthesize(
            A,
            B,
            d=D,
            cap=0,
            ident=ident,
            schemes=schemes,
            merge=merge,
            merge_op=merge_op,
            tab=tab,
        )
        for D in range(h + 1)
    }
    exact = results[h]
    deltas = []
    omegas = []
    for d in range(h):
        target = results[d].pool
        exact_partition = _partition(target, exact)
        delta = None
        for D in range(d, h + 1):
            if _partition(target, results[D]) == exact_partition:
                delta = D
                break
        if delta is None:  # impossible if h is a valid locality horizon
            raise AssertionError(f"no stabilization found for d={d} through h={h}")
        deltas.append(delta)
        omegas.append(delta - d)
    return {
        "h": h,
        "delta_below_h": deltas,
        "omega_fingerprint": omegas,
    }
