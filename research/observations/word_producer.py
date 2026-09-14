"""Infer interval questions and suffix actions; no prescribed comparison states."""
from .java_words import read_source
from .model import integer, require
from .word_kernel import SCHEMA, deltas, intervals, locate, seed_cuts, truth


def synthesize(source, *, max_contexts=8, max_actions=16):
    require(integer(max_contexts, 1, 8) and integer(max_actions, 1, 16), 'word observation budgets')
    ir = read_source(source); ds = deltas(ir); lower_ds = deltas(ir, True)
    ps = []; cuts = {}
    def exhausted(reason):
        return {'status': 'budget_exhausted', 'reason': reason, 'certificate': None}
    def add(p):
        if p['cut'] in cuts: return True
        if len(ps) + 1 >= max_contexts: return False
        cuts[p['cut']] = len(ps); ps.append(p); return True
    for i, test in enumerate(ir['tests']):
        for t in seed_cuts(test):
            if not add({'kind': 'seed', 'cut': t, 'test': i}): return exhausted('integer context budget')
    for i, p in enumerate(ps):
        for d in ds:
            if not add({'kind': 'pullback', 'cut': (p['cut'] - d) // 2, 'parent': i, 'delta': d}):
                return exhausted('integer context budget')
    parts = intervals(sorted(cuts)); n = len(parts)
    representatives = [p['upper'] if p['upper'] is not None else p['lower'] for p in parts]
    actions = {d: [locate(parts, 2 * x + d) for x in representatives] for d in ds}
    monoid = [{'map': list(range(n)), 'parent': None}]; ids = {tuple(range(n)): 0}; composition = []
    for i, node in enumerate(monoid):
        for d in lower_ds:
            f = tuple(node['map'][j] for j in actions[d])
            if f not in ids:
                if len(monoid) == max_actions: return exhausted('suffix action budget')
                ids[f] = len(monoid); monoid.append({'map': list(f), 'parent': {'state': i, 'delta': d}})
            composition.append({'state': i, 'delta': d, 'next': ids[f]})
    return {'status': 'candidate', 'certificate': {
        'schema': SCHEMA, 'source_ir': ir, 'questions': ps, 'intervals': parts,
        'actions': [{'delta': d, 'targets': actions[d]} for d in ds], 'origin': locate(parts, 0),
        'consumer': [[truth(p, t) for t in ir['tests']] for p in parts],
        'monoid': monoid, 'composition': composition}}
