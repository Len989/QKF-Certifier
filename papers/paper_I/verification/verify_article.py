#!/usr/bin/env python3
"""Finite checks accompanying Paper I. Python 3.10+, standard library only.

Run: python verification/verify_article.py --output verification/results.json
Finite checks support the displayed examples; they are not general proofs.
No QKF-Certifier installation, network access, or downloaded data is used.
"""
from __future__ import annotations
import argparse
import itertools as it
import json
import random
from pathlib import Path


class DSU:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, x, y):
        x, y = self.find(x), self.find(y)
        if x == y:
            return False
        self.p[max(x, y)] = min(x, y)
        return True


def canonical(labels):
    ids = {}
    return tuple(ids.setdefault(x, len(ids)) for x in labels)


def blocks(labels):
    return [[i for i, v in enumerate(labels) if v == x]
            for x in dict.fromkeys(labels)]


def value(table, xs, n):
    pos = 0
    for x in xs:
        pos = n * pos + x
    return table[pos]


def native_records(n, ops, copies=1):
    return [(oi, tuple(c*n+x for x in xs), c*n+value(tab, xs, n))
            for c in range(copies) for oi, (arity, tab) in enumerate(ops)
            for xs in it.product(range(n), repeat=arity)]


def close_records(uf, records):
    """Close a represented partial operation table under congruence."""
    changed = True
    while changed:
        changed = False
        seen = {}
        for op, args, result in records:
            key = (op, *(uf.find(x) for x in args))
            if key in seen:
                changed |= uf.union(result, seen[key])
            else:
                seen[key] = result
    return uf


def generated_congruence(n, ops, pairs):
    uf = DSU(n)
    for x, y in pairs:
        uf.union(x, y)
    close_records(uf, native_records(n, ops))
    return canonical([uf.find(i) for i in range(n)])


def quotient(n, ops, theta):
    theta = canonical(theta)
    m = len(set(theta))
    new_ops = []
    for arity, table in ops:
        slots = {}
        for xs in it.product(range(n), repeat=arity):
            key = tuple(theta[x] for x in xs)
            y = theta[value(table, xs, n)]
            if key in slots and slots[key] != y:
                return None
            slots[key] = y
        new_ops.append((arity, [slots[xs] for xs in it.product(range(m), repeat=arity)]))
    return m, new_ops


def row_pushout_kernel(n, ops, cells):
    """Raw native pushout: central and row tables, no action feedback."""
    uf = DSU(2*n)
    for a, c in cells:
        uf.union(n+a, c)
    close_records(uf, native_records(n, ops, 2))
    return canonical([uf.find(i) for i in range(n)])


def feedback(n, ops, nb, obs):
    theta = tuple(range(n))
    trajectory = [theta]
    while True:
        m, qops = quotient(n, ops, theta)
        pairs = []
        for b in range(nb):
            cells = [(theta[a], theta[c]) for bb, a, c in obs if bb == b]
            chi = row_pushout_kernel(m, qops, cells)
            pairs.extend((a, c) for a in range(n) for c in range(n)
                         if chi[theta[a]] == chi[theta[c]])
        nxt = generated_congruence(n, ops, pairs)
        if nxt == theta:
            return theta, trajectory
        assert len(set(nxt)) < len(set(theta))
        theta = nxt
        trajectory.append(theta)


def row_geometry(n, ops, cells):
    if not cells:
        return {}, tuple(range(n))
    h = {}
    for a, c in cells:
        assert a not in h or h[a] == c
        h[a] = c
    changed = True
    while changed:
        changed = False
        domain = list(h)
        for arity, tab in ops:
            for xs in it.product(domain, repeat=arity):
                a = value(tab, xs, n)
                c = value(tab, [h[x] for x in xs], n)
                if a in h:
                    assert h[a] == c, ('incoherent stabilized row', cells)
                else:
                    h[a] = c
                    changed = True
    kappa = generated_congruence(n, ops,
        [(a, c) for a in h for c in h if h[a] == h[c]])
    assert all((kappa[a] == kappa[c]) == (h[a] == h[c]) for a in h for c in h)
    return h, kappa


def structural_interface(n, ops, nb, obs):
    theta, trajectory = feedback(n, ops, nb, obs)
    m, qops = quotient(n, ops, theta)
    labels = [('central', theta[a]) for a in range(n)]
    details = []
    for b in range(nb):
        h, kappa = row_geometry(m, qops, [(theta[a], theta[c]) for bb, a, c in obs if bb == b])
        contact = {kappa[a]: c for a, c in h.items()}
        labels += [('central', contact[kappa[theta[a]]]) if kappa[theta[a]] in contact
                   else ('row', b, kappa[theta[a]]) for a in range(n)]
        details.append({'generated_domain': sorted(h), 'map': sorted(h.items()),
                        'row_kernel': blocks(kappa),
                        'forced_domain': [a for a in range(m) if kappa[a] in contact]})
    return canonical(labels), theta, trajectory, details


def depth(t):
    return 0 if len(t) == 1 else 1 + max(depth(c) for c in t[1:])


def subterms(t, out):
    if t not in out:
        for child in t[1:]:
            subterms(child, out)
        out.add(t)


def ground_presentation(n, ops, nb, obs):
    names = [(f'a{i}',) for i in range(n)]
    operators = [(f'b{i}',) for i in range(nb)]
    cell = lambda b, t: ('alpha', operators[b], t)
    equations = []
    for oi, (arity, table) in enumerate(ops):
        for xs in it.product(range(n), repeat=arity):
            native = (f'f{oi}', *(names[x] for x in xs))
            equations.append((native, names[value(table, xs, n)]))
            for b in range(nb):
                equations.append((cell(b, native),
                    (f'f{oi}', *(cell(b, names[x]) for x in xs))))
    equations.extend((cell(b, names[a]), names[c]) for b, a, c in obs)
    interface = names + [cell(b, names[a]) for b in range(nb) for a in range(n)]
    return equations, interface


def ground_interface(equations, interface, horizon):
    """Input-subterm DAG closure, independent of the row-pushout computation."""
    nodes = set()
    for s, t in equations:
        subterms(s, nodes)
        subterms(t, nodes)
    for t in interface:
        subterms(t, nodes)
    nodes = sorted((x for x in nodes if depth(x) <= horizon), key=repr)
    idx = {x: i for i, x in enumerate(nodes)}
    uf = DSU(len(nodes))
    for s, t in equations:
        if s in idx and t in idx:
            uf.union(idx[s], idx[t])
    records = [(t[0], tuple(idx[c] for c in t[1:]), idx[t]) for t in nodes if len(t) > 1]
    close_records(uf, records)
    return canonical([uf.find(idx[t]) for t in interface if t in idx])


def first_horizon(n, ops, nb, obs):
    theta = tuple(range(n))
    while True:
        pairs = [(a, c) for a in range(n) for c in range(n) if theta[a] == theta[c]]
        pairs += [(c, cc) for b, a, c in obs for bb, aa, cc in obs
                  if b == bb and theta[a] == theta[aa]]
        nxt = generated_congruence(n, ops, pairs)
        if nxt == theta:
            break
        theta = nxt
    labels = [('central', theta[a]) for a in range(n)]
    for b in range(nb):
        supplied = {theta[a]: theta[c] for bb, a, c in obs if bb == b}
        labels += [('central', supplied[theta[a]]) if theta[a] in supplied
                   else ('row', b, theta[a]) for a in range(n)]
    return canonical(labels)


def check_case(n, ops, nb, obs):
    equations, interface = ground_presentation(n, ops, nb, obs)
    c1 = ground_interface(equations, interface, 1)
    c2 = ground_interface(equations, interface, 2)
    predicted, theta, trajectory, details = structural_interface(n, ops, nb, obs)
    assert c1 == first_horizon(n, ops, nb, obs), (n, ops, nb, obs, 'horizon1')
    assert c2 == predicted, (n, ops, nb, obs, 'horizon2', c2, predicted)
    assert canonical(c2[:n]) == theta
    return c1, c2, theta, trajectory, details


def partitions(n):
    def visit(xs):
        if len(xs) == n:
            yield tuple(xs)
        else:
            for x in range(max(xs, default=-1)+2):
                yield from visit(xs+[x])
    yield from visit([])


def completions(n, ops, nb, obs, theta):
    q = quotient(n, ops, theta)
    if q is None:
        return None
    m, qops = q
    result = []
    for b in range(nb):
        row = []
        for tau in it.product(range(m), repeat=m):
            if any(tau[theta[a]] != theta[c] for bb, a, c in obs if bb == b):
                continue
            if all(tau[value(tab, xs, m)] == value(tab, [tau[x] for x in xs], m)
                   for arity, tab in qops for xs in it.product(range(m), repeat=arity)):
                row.append(tau)
        if not row:
            return None
        result.append(row)
    return result


def repair_audit(name, table, obs):
    n, ops, nb = 4, [(1, table)], 1
    c1, c2, theta, traj, details = check_case(n, ops, nb, obs)
    repairs = [p for p in partitions(n) if completions(n, ops, nb, obs, p) is not None]
    meet = canonical([tuple(p[a] for p in repairs) for a in range(n)])
    assert all(theta[a] != theta[c] or p[a] == p[c]
               for p in repairs for a in range(n) for c in range(n))
    return {'name': name, 'forced_carrier': blocks(theta),
            'repair_partitions': [blocks(p) for p in repairs],
            'repair_kernel': blocks(meet)}, repairs, meet, theta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path(__file__).with_name('results.json'))
    args = parser.parse_args()
    report = {'status': 'passed', 'scope': 'finite checks, not a formal proof of universal theorems'}
    tab4 = [0,2,0,0, 1,2,1,3, 0,2,2,0, 3,0,3,0]
    flag = check_case(4, [(2,tab4)], 1, [(0,0,0),(0,2,2),(0,3,0)])
    c1,c2,theta,traj,details = flag
    assert len(set(c1)) == 5 and len(set(c2)) == 3
    assert theta == (0,1,0,2) and all(c2[a] == c2[0] for a in range(4,8))
    assert generated_congruence(4,[(2,tab4)],[(0,3)]) == (0,0,0,0)
    report['four_element_example'] = {'N1': 5, 'N2': 3, 'horizon1': blocks(c1),
        'horizon2': blocks(c2), 'labels': ['0','1','2','3','r0','r1','r2','r3'],
        'all_row_values_equal_zero': True, 'forced_carrier': blocks(theta), 'row_geometry': details}
    amp = check_case(3,[(2,[0,0,0,0,0,0,0,1,0])],1,[(0,2,0)])
    assert amp[2] == (0,1,2) and all(amp[1][i] == amp[1][0] for i in range(3,6))
    report['amplification'] = {'protected': True, 'all_three_cells_forced': True}
    ext = check_case(2,[(2,[0,1,1,1])],1,[])
    assert len(set(ext[1])) == 4
    assert completions(2,[(2,[0,1,1,1])],1,[],(0,1)) is not None
    report['external_with_completion'] = {'interface_classes': 4, 'completion_exists': True}
    noleast, repairs, meet, theta = repair_audit('no_least_repair',[0,0,0,1],[(0,1,2)])
    assert (0,1,0,2) in repairs and (0,1,1,2) in repairs and (0,1,2,3) not in repairs
    assert meet == (0,1,2,3) and theta == (0,1,2,3)
    nonmono, repairs, meet, theta = repair_audit('nonmonotone',[0,0,0,0],[(0,0,1),(0,3,2)])
    assert (0,0,1,2) in repairs and (0,0,1,0) not in repairs and (0,0,0,0) in repairs
    gap, repairs, meet, theta = repair_audit('strict_gap',[1,1,1,2],[(0,0,2),(0,1,1),(0,2,0)])
    assert theta == (0,1,2,3) and meet == (0,1,0,2) and meet in repairs
    report['repair_examples'] = [noleast,nonmono,gap]
    sharp = []
    for n in range(2,9):
        obs = [(i-1,i-1,i) for i in range(1,n)]
        c1,c2,theta,traj,details = check_case(n,[(1,[0]*n)],n-1,obs)
        assert len(traj)-1 == n-1
        for k, stage in enumerate(traj):
            assert blocks(stage) == [list(range(k+1))]+[[a] for a in range(k+1,n)]
        sharp.append({'n': n, 'strict_rounds': len(traj)-1,
                      'trajectory': [blocks(x) for x in traj]})
    report['sharp_feedback'] = sharp
    differential = {'two_element_unary': 0, 'two_element_binary': 0, 'three_element_mixed': 0}
    possible = list(it.product(range(2),range(2),range(2)))
    observation_sets = [()] + [(x,) for x in possible] + list(it.combinations(possible,2))
    for arity, name in [(1,'two_element_unary'),(2,'two_element_binary')]:
        for tab in it.product(range(2),repeat=2**arity):
            for obs in observation_sets:
                check_case(2,[(arity,list(tab))],2,obs)
                differential[name] += 1
    rng = random.Random(20260911)
    for _ in range(64):
        ops = [(1,[rng.randrange(3) for _ in range(3)]),(2,[rng.randrange(3) for _ in range(9)])]
        obs = [tuple(rng.randrange(3) for _ in range(3)) for _ in range(rng.randrange(8))]
        check_case(3,ops,3,obs)
        differential['three_element_mixed'] += 1
    report['differential'] = {'families': differential, 'cases': sum(differential.values()),
        'random_seed': 20260911, 'comparison': 'entire labelled interface at horizons 1 and 2'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':'passed','differential_cases':sum(differential.values()),
                      'sharp_feedback_sizes':[2,8], 'output':str(args.output)},indent=2))


if __name__ == '__main__':
    main()
