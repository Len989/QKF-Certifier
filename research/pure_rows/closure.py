"""Verify chronological equalities AND complete represented-operation closure.

This module contains no fixed-point search. Lower inclusion: every successful
merge is derived from input cells/seeds or earlier equalities. Upper inclusion:
all seeds, represented operation tuples and allowed action feedback are closed.
These are different obligations, neither can replace the other.
"""
from __future__ import annotations
from .common import DSU, fields, integer, need, partition


def check_closure(size: int, native: list[tuple], seeds: list[tuple[int, int]],
                  proof: dict, feedback: tuple[int, int] | None = None) -> list[int]:
    fields(proof, ('partition', 'events'))
    claimed = partition(proof['partition'], size)
    events = proof['events']
    need(type(events) is list and len(events) <= size - 1, 'productive event bound')
    uf = DSU(size)
    for event in events:
        need(type(event) is list and bool(event) and type(event[0]) is str, 'equality event')
        kind = event[0]
        if kind == 'seed':
            need(len(event) == 2, 'seed event shape')
            a, b = seeds[integer(event[1], 0, len(seeds) - 1)]
        elif kind == 'native':
            need(len(event) == 3, 'native event shape')
            oi, xs, a = native[integer(event[1], 0, len(native) - 1)]
            oj, ys, b = native[integer(event[2], 0, len(native) - 1)]
            need(oi == oj and len(xs) == len(ys), 'operation symbol/arity differs')
            need(all(uf.find(x) == uf.find(y) for x, y in zip(xs, ys)),
                 'congruence premises must already hold')
        elif kind == 'feedback':
            need(len(event) == 4 and feedback is not None, 'action feedback not permitted here')
            n, nb = feedback
            row = integer(event[1], 0, nb - 1)
            x, y = integer(event[2], 0, n - 1), integer(event[3], 0, n - 1)
            need(uf.find(x) == uf.find(y), 'carrier equality must precede row feedback')
            a, b = (row + 1) * n + x, (row + 1) * n + y
        else:
            raise ValueError('unknown equality inference')
        need(uf.union(a, b), 'redundant/nonproductive equality event')
    need(uf.labels() == claimed, 'partition contains unjustified/missing recorded equalities')
    for a, b in seeds:
        need(claimed[a] == claimed[b], 'input equality omitted')
    seen = {}
    for op, args, result in native:
        key = (op, tuple(claimed[x] for x in args))
        need(key not in seen or seen[key] == claimed[result], 'native closure incomplete')
        seen[key] = claimed[result]
    if feedback is not None:
        n, nb = feedback
        for row in range(nb):
            images = {}
            for a in range(n):
                key, image = claimed[a], claimed[(row + 1) * n + a]
                need(key not in images or images[key] == image, 'action feedback incomplete')
                images[key] = image
    return list(claimed)
