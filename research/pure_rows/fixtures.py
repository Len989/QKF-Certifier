"""Explicit mathematical definitions; indices follow each table's displayed order."""
from .common import INPUT, THEORY


def make(n, ops, nb=1, cells=(), bops=()):
    return dict(schema=INPUT, theory=THEORY,
                carrier=dict(names=[str(a) for a in range(n)],
                             operations=[dict(name=f'f{i}', arity=k, table=list(t)) for i, (k, t) in enumerate(ops)]),
                operators=dict(names=[f'b{b}' for b in range(nb)],
                               operations=[dict(name=f'g{i}', arity=k, table=list(t)) for i, (k, t) in enumerate(bops)]),
                cells=[list(c) for c in cells])


def examples():
    yield 'I_6_1_amplification', make(3, [(2, [0,0,0, 0,0,0, 0,1,0])], cells=[(0,2,0)])
    yield 'I_6_2_obstruction', make(4, [(2, [0,2,0,0, 1,2,1,3, 0,2,2,0, 3,0,3,0])],
                                  cells=[(0,0,0), (0,2,2), (0,3,0)])
    yield 'I_6_3_external_completion', make(2, [(2, [0,1,1,1])])
    yield 'I_7_4_no_least_repair', make(4, [(1, [0,0,0,1])], cells=[(0,1,2)])
    yield 'I_7_5_nonmonotone_repair', make(4, [(1, [0,0,0,0])], cells=[(0,0,1),(0,3,2)])
    yield 'I_7_6_repair_kernel_gap', make(4, [(1, [1,1,1,2])], cells=[(0,0,2),(0,1,1),(0,2,0)])
    yield 'inconsistent_occurrences', make(2, [(2, [0,1,1,1])], 2,
                                          [(0,0,0),(0,0,1),(0,0,0)], [(1,[1,0])])
    yield 'unspecified_rows_disjoint', make(3, [], 3, [], [(2,[0,1,2,1,2,0,2,0,1])])
    yield 'noninjective_external_kernel', make(4, [(1,[0,0,0,3])], cells=[(0,1,0)])
    for n in range(2,9):
        yield f'I_5_5_sharp_{n}', make(n, [(1,[0]*n)], n-1, [(i-1,i-1,i) for i in range(1,n)])
