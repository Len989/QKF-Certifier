"""Check a chronological DAG of just the source-bound dependencies used."""
from research.ground_query.schema import fields, parse, require
from research.ground_query.checker import check as ground_check
from research.source_query.encoding import Graph
from research.source_lemmas.context import prepare, target_context, scope
from research.source_lemmas.terms import check_native, pair, roots
from .contract import canonical, digest, integer, snapshot

SCHEMA = 'qkf-direct-consumer-dependencies-v1'


def event_closure(proof):
    pending = list(proof['goals'][0]['path'])
    seen = set()
    while pending:
        i = pending.pop()
        if i not in seen:
            seen.add(i)
            event = proof['events'][i]
            if event['rule'] == 'congruence':
                pending.extend(e for path in event['premises'] for e in path)
    return sorted(seen)


def check(source, batch, raw):
    data = snapshot(raw)
    fields(data, ('schema', 'scope', 'nodes', 'goals'), 'direct dependencies')
    require(data['schema'] == SCHEMA, 'direct dependency version')
    ctx, requests = prepare(source, batch)
    require(canonical(data['scope']) == canonical(scope(ctx)), 'direct source/IR/G/width/algebra scope')
    require(type(data['nodes']) is list and len(data['nodes']) <= 8192, 'dependency budget')
    known, deps = {}, {}
    for node in data['nodes']:
        require(type(node) is dict and node.get('kind') in ('native', 'equality'), 'dependency kind')
        body = {k: v for k, v in node.items() if k != 'id'}
        require(type(node.get('id')) is str and node['id'] == digest(body) and node['id'] not in known,
                'unique content-bound dependency')
        if node['kind'] == 'native':
            fields(node, ('id', 'kind', 'entry'), 'native dependency')
            claim = check_native(ctx, node['entry'])['claim']
            parents = []
        else:
            fields(node, ('id', 'kind', 'claim', 'premises', 'via', 'request', 'proof'), 'derived dependency')
            parents = node['premises']
            require(type(parents) is list and all(type(p) is str for p in parents)
                    and len(parents) == len(set(parents)), 'distinct premise identities')
            require(all(p in known for p in parents), 'missing/forward/cyclic premise')
            claim = node['claim']
            require(type(claim) is list and len(claim) == 2, 'closed equality')
            residual = claim
            via = node['via']
            if via is not None:
                require(type(via) is str and via in known and known[via][0] == claim[0],
                        'checked prior equality with the exact left endpoint')
                residual = [known[via][1], claim[1]]
            inp, graph = parse(node['request']), Graph(ctx, node['request'])
            # The graph may contain needed congruence terms; it cannot add axioms.
            require(inp.equations == tuple(pair(graph, known[p]) for p in parents), 'exact proved premises')
            require(inp.queries and inp.queries[0] == pair(graph, residual), 'exact residual conclusion')
            require(all(a == b for a, b in inp.queries[1:]), 'additional proof-term declarations are reflexive')
            checked = ground_check(node['request'], node['proof'])
            require(checked['mode'] == 'entailment' and checked['goals'][0]['status'] == 'equal',
                    'a derived dependency requires a positive proof')
            require(node['proof']['models'] == [], 'positive dependency has no lower-model obligation')
            require(all(g['path'] == [] and g['lower_model'] is None for g in node['proof']['goals'][1:]),
                    'reflexive declarations cannot add proof assumptions')
            require(event_closure(node['proof']) == list(range(len(node['proof']['events']))), 'unused proof events')
            used = {e['equation'] for e in node['proof']['events'] if e['rule'] == 'axiom'}
            require(used == set(range(len(parents))), 'unused premise dependency')
            terms, pending = set(), [v for p in (*inp.equations, inp.queries[0]) for v in p]
            pending.extend(e[k] for e in node['proof']['events'] for k in ('left', 'right'))
            while pending:
                v = pending.pop()
                if v not in terms:
                    terms.add(v); pending.extend(inp.nodes[v][1])
            require(terms == set(range(len(inp.nodes))), 'unused proof terms')
            parents = [*parents, *([] if via is None else [via])]
        known[node['id']], deps[node['id']] = claim, parents
    require(type(data['goals']) is list and len(data['goals']) == len(requests), 'all independent goals')
    results, explanations, reached = [], [], set()
    for index, (q, item) in enumerate(zip(requests, data['goals'])):
        require(type(item) is dict and type(item.get('kind')) is str, 'consumer item')
        target = target_context(ctx, q)
        if item['kind'] == 'cached':
            fields(item, ('kind', 'previous'), 'prior exact goal')
            j = integer(item['previous'], 0, index - 1, 'earlier goal')
            require(canonical(q) == canonical(requests[j]), 'exact cached consumer')
            results.append(snapshot(results[j])); explanations.append(snapshot(explanations[j]))
            continue
        if item['kind'] == 'node':
            fields(item, ('kind', 'node'), 'checked goal')
            root = item['node']
            require(target.domain and type(root) is str and root in known and known[root] == roots(target),
                    'dependency does not prove this independent consumer')
            pending, used = [root], set()
            while pending:
                n = pending.pop()
                if n not in used:
                    used.add(n); pending.extend(deps[n])
            reached.update(used)
            results.append(dict(status='certified', reason='consumer_closed', target_checked=True,
                                all_positive_widths=target.width is None, source_refutation=False))
            explanations.append(dict(kind='direct_dependencies', root=root,
                nodes=[snapshot(n) for n in data['nodes'] if n['id'] in used]))
        elif item['kind'] == 'empty':
            fields(item, ('kind',), 'empty domain')
            require(not target.domain, 'nonempty domain')
            results.append(dict(status='verified_empty_domain', reason='empty_guard', target_checked=False))
            explanations.append(dict(kind='empty_domain', guards=target.guards, width=target.request['width']))
        elif item['kind'] == 'witness':
            fields(item, ('kind', 'certificate'), 'concrete violation')
            from research.source_query.checker import check as source_check
            checked = source_check(source, q, item['certificate'])
            require(checked['status'] == 'refuted', 'concrete violation required')
            results.append(checked)
            explanations.append(dict(kind='concrete_violation', certificate=item['certificate']))
        else:
            raise ValueError('unknown direct goal')
    require(reached == set(known), 'unreachable dependency nodes')
    return results, explanations
