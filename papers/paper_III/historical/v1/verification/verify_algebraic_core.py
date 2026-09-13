"""Targeted mathematical checks for the three-paper contract; Python 3.10+.

Run from the extracted package. The frozen research relation oracle is shipped
under evidence_sources. Pass --certifier-root for the optional real-source replay
checks against the public repository. Finite checks are not general proofs.
"""
from __future__ import annotations

import argparse
import itertools as it
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "evidence_sources"))
from relation_matrix_exact import RelationMatrixExact, CENTRAL


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
        self.p[y] = x
        return True


def depth(t):
    return 0 if len(t) == 1 else 1 + max(depth(x) for x in t[1:])


def collect(t, out):
    if t in out:
        return
    for c in t[1:]:
        collect(c, out)
    out.add(t)


def close_ground(equations, queries, horizon=None):
    """Independent, deliberately simple, full input-subterm congruence closure."""
    all_nodes = set()
    for a, b in equations:
        collect(a, all_nodes)
        collect(b, all_nodes)
    for q in queries:
        collect(q, all_nodes)
    nodes = sorted((t for t in all_nodes if horizon is None or depth(t) <= horizon), key=repr)
    idx = {t: i for i, t in enumerate(nodes)}
    uf = DSU(len(nodes))
    for a, b in equations:
        if a in idx and b in idx:
            uf.union(idx[a], idx[b])
    rounds = 0
    while True:
        rounds += 1
        changed = False
        signatures = {}
        for t in nodes:
            sig = (t[0], *(uf.find(idx[c]) for c in t[1:]))
            if sig in signatures:
                changed |= uf.union(idx[t], signatures[sig])
            else:
                signatures[sig] = idx[t]
        if not changed:
            break
    return {t: uf.find(idx[t]) for t in nodes}, rounds


def native_value(tab, args, n):
    i = 0
    for a in args:
        i = n * i + a
    return tab[i]


def polyadic_ground(n, ops, observations):
    names = [(f"a{i}",) for i in range(n)]
    cell = lambda a, b: ("tau", names[a], names[b])
    equations = []
    for oi, (arity, tab) in enumerate(ops):
        op = f"f{oi}"
        for xs in it.product(range(n), repeat=arity):
            native = (op, *(names[x] for x in xs))
            value = native_value(tab, xs, n)
            equations.append((native, names[value]))
            for context in range(n):
                equations.append((("tau", native, names[context]), (op, *(cell(x, context) for x in xs))))
                equations.append((("tau", names[context], native), (op, *(cell(context, x) for x in xs))))
    equations.extend((cell(*xs), names[y]) for xs, y in observations)
    return equations, names + [cell(a, b) for a, b in it.product(range(n), repeat=2)], names, cell


def relation_case(n, ops, observations):
    equations, queries, names, cell = polyadic_ground(n, ops, observations)
    classes, _ = close_ground(equations, queries)
    matrix = RelationMatrixExact(n, ops, observations)
    rounds = matrix.solve()
    # Compare the ENTIRE carrier/cell interface, not only carrier-valued cells.
    labels = [(CENTRAL, a) for a in range(n)] + [(('R', b), a) for a, b in it.product(range(n), repeat=2)]
    for i, j in it.product(range(len(queries)), repeat=2):
        c, a = labels[i]
        d, b = labels[j]
        assert (classes[queries[i]] == classes[queries[j]]) == ((a, b) in matrix.R[c, d]), (n, ops, observations, i, j)
    # Explicitly recheck closure after solve rather than trust its round counter.
    assert not matrix.quotient_feedback()
    assert not matrix.compatibility()
    assert not matrix.transitivity()
    return rounds, len(queries) ** 2


def check_relation():
    cells = [((a, b), y) for a, b, y in it.product(range(2), repeat=3)]
    observation_sets = [()] + [(x,) for x in cells] + list(it.combinations(cells, 2))
    counts = {"all_two_element_binary_tables": 0, "all_two_element_unary_tables": 0, "random_three_element_mixed": 0}
    max_rounds = pair_checks = 0
    for arity, family in [(2, "all_two_element_binary_tables"), (1, "all_two_element_unary_tables")]:
        for tab in it.product(range(2), repeat=2**arity):
            for observations in observation_sets:
                rounds, pairs = relation_case(2, [(arity, list(tab))], observations)
                counts[family] += 1
                max_rounds = max(max_rounds, rounds)
                pair_checks += pairs
    rng = random.Random(20260911)
    for _ in range(64):
        ops = [(1, [rng.randrange(3) for _ in range(3)]), (2, [rng.randrange(3) for _ in range(9)])]
        observations = [((rng.randrange(3), rng.randrange(3)), rng.randrange(3)) for _ in range(rng.randrange(6))]
        rounds, pairs = relation_case(3, ops, observations)
        counts["random_three_element_mixed"] += 1
        max_rounds = max(max_rounds, rounds)
        pair_checks += pairs
    return {"status": "passed", "cases": sum(counts.values()), "families": counts, "interface_pair_checks": pair_checks, "maximum_rounds_observed": max_rounds}


def check_flagship():
    tab = [0, 2, 0, 0, 1, 2, 1, 3, 0, 2, 2, 0, 3, 0, 3, 0]
    a = [(f"a{i}",) for i in range(4)]
    b = ("b",)
    row = lambda x: ("alpha", b, x)
    equations = []
    for x, y in it.product(range(4), repeat=2):
        native = ("f", a[x], a[y])
        equations.append((native, a[tab[4*x+y]]))
        equations.append((("alpha", b, native), ("f", row(a[x]), row(a[y]))))
    equations.extend((row(a[x]), a[y]) for x, y in [(0, 0), (2, 2), (3, 0)])
    interface = a + [row(x) for x in a]
    stages = {}
    for d in [0, 1, 2]:
        classes, rounds = close_ground(equations, interface, d)
        groups = {}
        for i, term in enumerate(interface):
            if term in classes:
                groups.setdefault(classes[term], []).append(str(i) if i < 4 else f"r{i-4}")
        stages[str(d)] = {"interface_blocks": sorted(groups.values()), "carrier_blocks": [[i for i in range(4) if classes[a[i]] == c] for c in sorted({classes[t] for t in a})], "cc_passes": rounds}
    c1, _ = close_ground(equations, interface, 1)
    c2, _ = close_ground(equations, interface, 2)
    assert c1[a[0]] != c1[a[2]] and c2[a[0]] == c2[a[2]]
    assert len(set(c1[t] for t in interface)) == 5
    # The dossier's expectation of a remaining external cell is false for this
    # exact table: f(1,0)=1, f(1,3)=3, and r0=r3 imply r1=r3=0.
    assert len(set(c2[t] for t in interface)) == 3
    assert all(c2[row(t)] == c2[a[0]] for t in a)
    domain = [0, 2, 3]
    h = {0: 0, 2: 2, 3: 0}
    assert all(h[tab[4*x+y]] == tab[4*h[x]+h[y]] for x, y in it.product(domain, repeat=2))
    # A small countermodel for horizon one: native carrier + one external r1.
    # Every active term evaluates to its class. Undefined operation tuples may
    # be assigned a default per sort; no such choice changes these classes.
    return {"status": "passed", "lambda_0_2": 2, "N1": 5, "N2": 3, "all_row_values_forced_to_zero": True, "dossier_correction": "The missing cell r1 is forced, not external, for the table in I ex:cepobstruction.", "stages": stages}


def check_feedback_necessity():
    observations = [((0, 0), 0), ((0, 0), 1)]
    ops = [(2, [0, 1, 1, 1])]
    full = RelationMatrixExact(2, ops, observations)
    full.solve()
    incomplete = RelationMatrixExact(2, ops, observations)
    incomplete.quotient_feedback = lambda: False
    incomplete.solve()
    assert len(full.known()) == 4 and len(incomplete.known()) == 1
    return {"status": "passed", "native_table": ops[0][1], "observations": observations, "known_cells_with_feedback": len(full.known()), "known_cells_without_feedback": len(incomplete.known())}


def gamma(pair):
    z, o = pair
    return {x for x in [0, 1] if not x & z and x & o == o}


KB = [(1, 0), (0, 1), (0, 0)]


def signature(rows):
    return sum(bit << (2*i+j) for i, pair in enumerate(rows) for j, bit in enumerate(pair))


def check_signatures():
    targets = {"and": lambda x, y: x & y, "or": lambda x, y: x | y, "xor": lambda x, y: x ^ y}
    results = {}
    row_inputs = list(it.product(KB, repeat=2))
    for name, operation in targets.items():
        exact = [{operation(x, y) for x in gamma(a) for y in gamma(b)} for a, b in row_inputs]
        precise = [next(k for k in KB if gamma(k) == values) for values in exact]
        best = signature(precise)
        sound = []
        for rows in it.product(KB, repeat=9):
            if all(values <= gamma(out) for values, out in zip(exact, rows)):
                sig = signature(rows)
                assert sig & ~best == 0
                sound.append(sig)
        expected = 64 if name != "xor" else 16
        assert len(sound) == len(set(sound)) == expected
        assert len(sound) == 2 ** best.bit_count()
        sound_set = set(sound)
        for x, y in it.product(sound, repeat=2):
            assert x | y in sound_set and x & y in sound_set
        results[name] = {"sound_semantic_classes": len(sound), "precision_features": best.bit_count(), "best_signature": f"{best:05x}", "meet_pairs_checked": len(sound)**2}
    return {"status": "passed", "valid_tables_enumerated_per_target": 3**9, "targets": results}


def check_real_certificates(certifier_root):
    if certifier_root is None:
        return {"status": "not_requested", "reason": "Supply --certifier-root PATH to an extracted QKF-Certifier checkout for source replay checks."}
    certifier_root = Path(certifier_root).resolve()
    sys.path.insert(0, str(certifier_root / "src"))
    from qkf_certifier import verify, check_certificate, inspect
    examples = certifier_root / "examples" / "ntmy"
    results = {}
    for name in ["and", "or", "xor"]:
        bundle = {"program": (examples / f"{name}.mlir").read_bytes().decode("utf-8")}
        if name == "xor":
            bundle["meet"] = (examples / "meet.mlir").read_bytes().decode("utf-8")
        produced = verify(bundle, name)
        checked = check_certificate(bundle, name, produced["certificate"])
        info = inspect(bundle)
        assert checked["status"] == "certified" and checked["optimal"] and checked["all_positive_widths"]
        results[name] = {"status": checked["status"], "optimal": checked["optimal"], "rewrite_steps": checked["rewrite_steps"], "semantic_signature": info["semantic_signature"], "source_hashes": checked["source_hashes"]}
    return {"status": "passed", "examples": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--certifier-root", type=Path)
    args = parser.parse_args()
    start = time.perf_counter()
    result = {"purpose": "finite evidence for statements; not a proof of universal correctness", "relation": check_relation(), "flagship": check_flagship(), "feedback": check_feedback_necessity(), "signatures": check_signatures(), "certificates": check_real_certificates(args.certifier_root)}
    if result["certificates"]["status"] == "passed":
        for name, row in result["signatures"]["targets"].items():
            assert row["best_signature"] == result["certificates"]["examples"][name]["semantic_signature"]
    result["elapsed_seconds"] = round(time.perf_counter()-start, 3)
    result["status"] = "passed"
    path = ROOT / "core_results.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n")
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
