"""Isolated conformance worker using retained full-universe engine.close.

This is intentionally NOT a dependency of the producer or semantic checker.
The typed bounded universe is enumerated only in this reference experiment.
"""

from itertools import product
import json
from pathlib import Path
import sys


def rewrite_gap():
    """Independent sequential rewriting on the tiny complete unary universe."""
    from .fixtures import power, term
    p, q, r = (term(x) for x in ('p', 'q', 'r'))
    equations = [(p, power(2, r)), (q, power(2, r))]
    def neighbors(t):
        out = set()
        for a, b in equations:
            if t == a:
                out.add(b)
            if t == b:
                out.add(a)
        if len(t) > 1:
            out.update(term('f', a) for a in neighbors(t[1]))
        return out
    for d in range(1, 4):
        universe = {power(k, c) for k in range(d + 1) for c in (p, q, r)}
        seen, stack = {power(1, p)}, [power(1, p)]
        while stack:
            for nxt in neighbors(stack.pop()) & universe - seen:
                seen.add(nxt)
                stack.append(nxt)
        if power(1, q) in seen:
            return {'congruence': 2, 'sequential_rewrite': d}
    raise ValueError('rewrite reference did not close at depth three')


def run(root):
    prototype = Path(__file__).resolve().parents[2] / 'papers/paper_II/prototype'
    sys.path.insert(0, str(prototype))
    from engine import Term, close, depth
    from .schema import load_json, parse
    manifest = load_json(root / 'CASES.json')
    results = {}
    for case in manifest:
        request = load_json(root / case['name'] / 'request.json')
        inp = parse(request)
        terms = []
        for op, args in inp.nodes:
            terms.append(Term(op, tuple(terms[a] for a in args)))
        equations = [(terms[a], terms[b]) for a, b in inp.equations]
        pool = {sort: set() for sort in inp.sorts}
        levels = []
        for d in range(inp.horizon + 1):
            old = {sort: sorted(ts, key=lambda t: (depth(t), t.pretty())) for sort, ts in pool.items()}
            for op, spec in inp.signature.items():
                for args in product(*(old[sort] for sort in spec['args'])):
                    pool[spec['result']].add(Term(op, args))
            all_terms = sorted(set().union(*pool.values()), key=lambda t: (depth(t), t.pretty()))
            uf, admitted = close(all_terms, equations, {op: len(spec['args']) for op, spec in inp.signature.items()})
            labels, classes = [], {}
            for i, t in enumerate(terms):
                if inp.depths[i] > d:
                    labels.append(None)
                    continue
                key = uf.find(t)
                if key not in classes:
                    classes[key] = len(classes)
                labels.append(classes[key])
            levels.append({'horizon': d, 'pool_size': len(all_terms), 'active_equations': admitted, 'labels': labels})
        results[case['name']] = levels
    (root / 'REFERENCE.json').write_text(json.dumps(results, sort_keys=True) + '\n')
    return {'cases': len(results), 'thresholds': sum(len(v) for v in results.values())}


if __name__ == '__main__':
    print(json.dumps(run(Path(sys.argv[1])), sort_keys=True))
