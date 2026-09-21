"""Slice checked PR44 derivations; no search or legacy model construction."""
from research.signed_compact import dag
from research.ground_query.schema import INPUT_SCHEMA, parse
from research.source_query.encoding import Graph
from research.source_lemmas.checker import load
from research.source_lemmas.context import target_context, scope
from research.source_lemmas.terms import term, intern, pair, roots
from .contract import digest, snapshot, require
from .direct import SCHEMA, event_closure


def slice_ground(ctx, old_request, proof, premises, residual):
    """Rename terms/events while retaining the actual checked derivation."""
    keep = event_closure(proof)
    axioms = sorted({proof['events'][i]['equation'] for i in keep if proof['events'][i]['rule'] == 'axiom'})
    before, after = Graph(ctx, old_request), Graph(ctx)
    equations = [pair(after, premises[i]) for i in axioms]
    query = pair(after, residual)
    def rename(i):
        return intern(after, term(before, i))
    events, event_map = [], {old: new for new, old in enumerate(keep)}
    for i in keep:
        e = snapshot(proof['events'][i])
        e['left'], e['right'] = rename(e['left']), rename(e['right'])
        if e['rule'] == 'axiom':
            e['equation'] = axioms.index(e['equation'])
        else:
            e['premises'] = [[event_map[j] for j in path] for path in e['premises']]
        events.append(e)
    reachable, pending = set(), [v for p in [*equations, query] for v in p]
    while pending:
        i = pending.pop()
        if i not in reachable:
            reachable.add(i); pending.extend(after.nodes[i]['args'])
    extra = set(range(len(after.nodes))) - reachable
    # A used congruence term can survive deletion of an unused equation that
    # originally declared it. Reflexive queries retain its syntax, not an axiom.
    support = sorted(extra - {a for i in extra for a in after.nodes[i]['args']})
    req = dict(schema=INPUT_SCHEMA, sorts=['Word', 'Bool'], signature=after.signature,
               nodes=after.nodes, equations=[list(p) for p in equations],
               queries=[list(query), *[[i, i] for i in support]])
    # Reuse the full signature, but no unused equation or proof event.
    inp = parse(req)
    goal = snapshot(proof['goals'][0]); goal['path'] = [event_map[i] for i in goal['path']]
    declarations = [dict(status='equal', path=[], depth=inp.depths[i], lower_model=None) for i in support]
    cert = dict(schema=proof['schema'], request_sha256=inp.identity, mode='entailment',
                horizon=goal['depth'], events=events, models=[], goals=[goal, *declarations])
    require(goal['lower_model'] is None, 'entailment export, not threshold minimization')
    return req, cert, axioms


def extract(source, batch, packet):
    presentation, results = load(source, batch, packet)
    raw = dag.unpack(packet)
    if any(r['status'] == 'unresolved' for r in results):
        return 'native_batch', raw, dict(reason='retain_scoped_lower_models')
    ctx = presentation.context()
    native = {n['id']: n for n in presentation.native()}
    lemmas = {n['id']: n for n in presentation.lemmas()}
    nodes, rewritten = [], {}
    def emit(body):
        node = dict(id=digest(body), **body)
        if all(n['id'] != node['id'] for n in nodes):
            nodes.append(node)
        return node['id']
    def dependency(old):
        if old not in rewritten:
            if old in native:
                rewritten[old] = emit(dict(kind='native', entry=native[old]))
            else:
                lemma = lemmas[old]
                rewritten[old] = equality(lemma['claim'], lemma, dict(
                    native=lemma['native_count'], lemmas=lemma['prior_lemmas']))
        return rewritten[old]
    def equality(claim, item, epoch):
        basis = item['basis']
        ids = basis['native'] + basis['lemmas']
        claims = presentation.premises(basis, epoch)
        residual = presentation.residual_claim(claim, item['via_lemma'], epoch)
        old = presentation.request(residual, basis, epoch)
        req, cert, selected = slice_ground(ctx, old, item['certificate'], claims, residual)
        parents = [dependency(ids[i]) for i in selected]
        via = None if item['via_lemma'] is None else dependency(item['via_lemma'])
        return emit(dict(kind='equality', claim=claim, premises=parents, via=via, request=req, proof=cert))
    goals = []
    for q, item in zip(batch['requests'], raw['items']):
        kind = item['kind']
        if kind == 'lemma':
            goals.append(dict(kind='node', node=dependency(item['lemma'])))
        elif kind == 'ground':
            goals.append(dict(kind='node', node=equality(roots(target_context(ctx, q)), item, item['epoch'])))
        elif kind == 'cached_goal':
            goals.append(dict(kind='cached', previous=item['previous']))
        else:
            goals.append(snapshot(item))
    data = dict(schema=SCHEMA, scope=scope(ctx), nodes=nodes, goals=goals)
    stats = dict(native_available=len(native), native_retained=sum(n['kind'] == 'native' for n in nodes),
                 lemmas_available=len(lemmas), dependencies=len(nodes),
                 retained_events=sum(len(n['proof']['events']) for n in nodes if n['kind'] == 'equality'))
    return 'native_direct', data, stats
