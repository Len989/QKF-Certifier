"""Plain unfiltered congruence closure control; no PR40 producer or activation."""
from collections import deque
from research.ground_query.schema import parse, PROOF_SCHEMA


def prove(request):
    inp = parse(request)
    parent = list(range(len(inp.nodes)))
    adj = [[] for _ in parent]
    events = []
    passes, signatures = 0, 0
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def path(a, b):
        prev, todo = {a: None}, deque([a])
        while todo and b not in prev:
            u = todo.popleft()
            for v, eid in adj[u]:
                if v not in prev:
                    prev[v] = (u, eid)
                    todo.append(v)
        if b not in prev:
            raise ValueError('ordinary control missing earlier equality')
        ids = []
        while b != a:
            b, eid = prev[b]
            ids.append(eid)
        return list(reversed(ids))
    def merge(a, b, rule, detail):
        if find(a) == find(b):
            return False
        depth = max(inp.depths[a], inp.depths[b])
        if rule == 'congruence':
            depth = max([depth] + [events[i]['depth'] for p in detail['premises'] for i in p])
        eid = len(events)
        events.append({'rule': rule, 'left': a, 'right': b, 'depth': depth, **detail})
        adj[a].append((b, eid))
        adj[b].append((a, eid))
        parent[find(b)] = find(a)
        return True
    for i, (a, b) in enumerate(inp.equations):
        merge(a, b, 'axiom', {'equation': i})
    changed = True
    while changed:
        changed, seen = False, {}
        passes += 1
        for i, (op, args) in enumerate(inp.nodes):
            signatures += 1
            key = op, tuple(find(a) for a in args)
            if key in seen:
                j = seen[key]
                if find(i) != find(j):
                    premises = [path(a, b) for a, b in zip(args, inp.nodes[j][1])]
                    changed |= merge(i, j, 'congruence', {'premises': premises})
            else:
                seen[key] = i
    models, goals = [], []
    if any(find(a) != find(b) for a, b in inp.queries):
        classes = {s: {} for s in inp.sorts}
        values = []
        for i, sort in enumerate(inp.node_sorts):
            group = classes[sort]
            root = find(i)
            if root not in group: group[root] = len(group)
            values.append(group[root])
        tables = {op: {} for op in inp.signature}
        for i, (op, args) in enumerate(inp.nodes):
            key = tuple(values[a] for a in args)
            if key in tables[op] and tables[op][key] != values[i]:
                raise ValueError('ordinary control model inconsistency')
            tables[op][key] = values[i]
        models.append({'horizon': inp.horizon, 'domains': {s: max(1, len(v)) for s, v in classes.items()},
                       'operations': {op: {'default': 0, 'rows': [{'args': list(a), 'value': v}
                                       for a, v in sorted(rows.items())]} for op, rows in tables.items()}})
    for a, b in inp.queries:
        if find(a) == find(b):
            ids = path(a, b)
            depth = max([inp.depths[a], inp.depths[b]] + [events[i]['depth'] for i in ids])
            goals.append({'status': 'equal', 'path': ids, 'depth': depth, 'lower_model': None})
        else:
            goals.append({'status': 'not_entailed', 'model': 0})
    # Give the control the same reachable-proof compaction as the query route.
    total_merges = len(events)
    needed, todo = set(), [i for goal in goals if goal['status'] == 'equal' for i in goal['path']]
    while todo:
        i = todo.pop()
        if i not in needed:
            needed.add(i)
            todo.extend(j for p in events[i].get('premises', []) for j in p)
    remap = {old: new for new, old in enumerate(sorted(needed))}
    events = [{**events[i], **({'premises': [[remap[j] for j in p] for p in events[i]['premises']]}
                            if 'premises' in events[i] else {})} for i in sorted(needed)]
    for goal in goals:
        if goal['status'] == 'equal': goal['path'] = [remap[i] for i in goal['path']]
    return {'schema': PROOF_SCHEMA, 'request_sha256': inp.identity, 'mode': 'entailment',
            'horizon': inp.horizon, 'events': events, 'models': models, 'goals': goals}, {
            'passes': passes, 'signature_visits': signatures, 'merges': total_merges,
            'proof_events': len(events), 'activation_layers': 0}
