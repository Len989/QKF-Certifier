"""Typed adapter over the retained incremental Paper II query-subterm engine.

No bounded-universe enumeration is used here. The retained engine still stores
one partition per activation horizon; this PR makes no new complexity claim.
"""

from .schema import PROOF_SCHEMA, parse, require
from .prototype.terms import Term
from .prototype.visibility_cc import AxiomReason
from .prototype.visibility_cc_fast import IncrementalVisibilityCC
from .prototype.certificates import CertifiedProofStore


def search(request, horizon=None):
    inp = parse(request)
    horizon = inp.horizon if horizon is None else horizon
    require(type(horizon) is int and 0 <= horizon <= inp.horizon, 'search horizon')
    require(all(max(inp.depths[a], inp.depths[b]) <= horizon for a, b in inp.queries), 'inactive query')
    terms = []
    for i, (op, args) in enumerate(inp.nodes):
        terms.append(Term(op, tuple(terms[a] for a in args), i))
    equations = [(terms[a], terms[b]) for a, b in inp.equations]
    queries = list(dict.fromkeys(terms[i] for pair in inp.queries for i in pair))
    run = IncrementalVisibilityCC(equations, queries, horizon=horizon).run()
    require(set(run.nodes) == set(terms), 'producer constructed non-query terms')
    return inp, terms, run


def _model(inp, terms, run, horizon):
    snapshot = run.snapshots[horizon]
    classes = {sort: {} for sort in inp.sorts}
    values = {}
    for i, term in enumerate(terms):
        if inp.depths[i] <= horizon:
            group = classes[inp.node_sorts[i]]
            key = snapshot[term]
            if key not in group:
                group[key] = len(group)
            values[i] = group[key]
    domains = {sort: max(1, len(group)) for sort, group in classes.items()}
    tables = {op: {} for op in inp.signature}
    for i, (op, args) in enumerate(inp.nodes):
        if i in values:
            key, value = tuple(values[a] for a in args), values[i]
            require(key not in tables[op] or tables[op][key] == value, 'model is not well defined')
            tables[op][key] = value
    return {'horizon': horizon, 'domains': domains, 'operations': {
        op: {'default': 0, 'rows': [{'args': list(args), 'value': value}
                                   for args, value in sorted(table.items())]}
        for op, table in tables.items()}}


def prove(request, mode='entailment', horizon=None):
    require(mode in ('entailment', 'exact_threshold'), 'proof mode')
    inp, terms, run = search(request, horizon)
    proof = CertifiedProofStore.from_run(run)
    ids = {term: i for i, term in enumerate(terms)}
    # Iterative extraction avoids recursion proportional to proof dependency depth.
    selected = set()
    for a, b in inp.queries:
        if run.exact_equal(terms[a], terms[b]):
            stack = list(proof.top_path(terms[a], terms[b]))
            while stack:
                eid = stack.pop()
                if eid not in selected:
                    selected.add(eid)
                    stack.extend(proof.event_dependencies(eid))
    selected = sorted(selected)
    remap = {old: new for new, old in enumerate(selected)}
    events, models, model_ids, goals = [], [], {}, []
    for eid in selected:
        certified = proof.certified[eid]
        ev, reason = certified.event, certified.event.reason
        item = {'left': ids[ev.left], 'right': ids[ev.right], 'depth': ev.level}
        if isinstance(reason, AxiomReason):
            item.update(rule='axiom', equation=reason.equation_index)
        else:
            premise_iter = iter(certified.premise_paths)
            paths = [() if x == y else next(premise_iter) for x, y in reason.argument_pairs]
            item.update(rule='congruence', premises=[[remap[p] for p in path] for path in paths])
        events.append(item)

    def model_at(d):
        if d not in model_ids:
            model_ids[d] = len(models)
            models.append(_model(inp, terms, run, d))
        return model_ids[d]

    for a, b in inp.queries:
        s, t = terms[a], terms[b]
        d = run.first_equal(s, t)
        if d is None:
            goals.append({'status': 'not_entailed' if run.horizon == inp.horizon else 'not_visible',
                          'model': model_at(run.horizon)})
        else:
            lower = model_at(d - 1) if mode == 'exact_threshold' and d > max(inp.depths[a], inp.depths[b]) else None
            goals.append({'status': 'equal', 'path': [remap[i] for i in proof.top_path(s, t)],
                          'depth': d, 'lower_model': lower})
    certificate = {'schema': PROOF_SCHEMA, 'request_sha256': inp.identity, 'mode': mode,
                   'horizon': run.horizon, 'events': events, 'models': models, 'goals': goals}
    # Statistics are deliberately outside the semantic certificate.
    return certificate, dict(run.stats, input_nodes=len(inp.nodes), proof_events=len(events),
                             models=len(models), queries=len(goals), added_terms=0)
