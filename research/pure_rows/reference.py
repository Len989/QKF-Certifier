"""Independent RAW typed ground-subterm closure, for tests/experiments only.

No production closure/feedback/geometry code is used. This is the second route
from Paper I §10, adapted from its supplement to explicit two-sorted signatures.
It does not enumerate the full depth-two universe, nor call the signed profiles.
"""
from __future__ import annotations
import itertools
from .common import presentation


def ground(raw_input, horizon=2):
    p = presentation(raw_input)
    terms = []
    index = {}
    depths = []

    def node(sort, head, args=()):
        key = (sort, head, tuple(args))
        if key not in index:
            index[key] = len(terms)
            terms.append(key)
            depths.append(0 if not args else 1 + max(depths[a] for a in args))
        return index[key]

    names = [node('A', ('nameA', a)) for a in range(len(p['carrier']['names']))]
    operators = [node('B', ('nameB', b)) for b in range(len(p['operators']['names']))]
    alpha = lambda b, a: node('A', ('action',), (operators[b], a))
    rows = [[alpha(b, a) for a in names] for b in range(len(operators))]
    equations = []
    for sort, desc, constants in [('A', p['carrier'], names), ('B', p['operators'], operators)]:
        for oi, op in enumerate(desc['operations']):
            for args, out in zip(itertools.product(range(len(constants)), repeat=op['arity']), op['table']):
                head = ('native' + sort, oi)
                left = node(sort, head, tuple(constants[a] for a in args))
                equations.append((left, constants[out]))
                if sort == 'A':
                    for b in range(len(operators)):
                        equations.append((alpha(b, left), node('A', head, tuple(rows[b][a] for a in args))))
    equations.extend((rows[b][a], names[c]) for b, a, c in p['cells'])
    active = [i for i, d in enumerate(depths) if d <= horizon]
    classes = list(range(len(terms)))

    def merge(a, b):
        x, y = classes[a], classes[b]
        if x == y:
            return False
        lo, hi = min(x, y), max(x, y)
        # Deliberately independent, transparent label replacement oracle.
        for i in active:
            if classes[i] == hi:
                classes[i] = lo
        return True

    for a, b in equations:
        if depths[a] <= horizon and depths[b] <= horizon:
            merge(a, b)
    while True:
        changed = False
        seen = {}
        for i in active:
            sort, head, args = terms[i]
            if not args:
                continue
            key = sort, head, tuple(classes[a] for a in args)
            if key in seen:
                changed |= merge(i, seen[key])
            else:
                seen[key] = i
        if not changed:
            break
    ids = {}
    order = names + [a for row in rows for a in row]
    labels = [ids.setdefault(classes[a], len(ids)) for a in order]
    return dict(partition=labels, represented_nodes=len(active),
                active_equations=sum(depths[a] <= horizon and depths[b] <= horizon for a, b in equations))
