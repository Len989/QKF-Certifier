"""Standalone semantic checker. No imports of the producer or closure engine.

Positive proofs establish only consequences of the supplied finite E. A model
at D checks EVERY equation with both endpoints active at D. Sparse operation
tables have an explicit well-sorted default, hence define total operations.
"""

import json
from .schema import MAX_STEPS, PROOF_SCHEMA, canonical, fields, index, parse, require


def check_model(inp, model, horizon):
    fields(model, ('horizon', 'domains', 'operations'), 'model')
    require(type(model['horizon']) is int and model['horizon'] == horizon, 'model horizon')
    domains, operations = model['domains'], model['operations']
    fields(domains, inp.sorts, 'model sorts')
    for size in domains.values():
        require(type(size) is int and 0 < size <= MAX_STEPS, 'nonempty model domain')
    fields(operations, inp.signature, 'model signature')
    tables, defaults = {}, {}
    for op, spec in inp.signature.items():
        desc = operations[op]
        fields(desc, ('default', 'rows'), 'model operation')
        defaults[op] = index(desc['default'], domains[spec['result']], 'operation default')
        rows = desc['rows']
        require(type(rows) is list and len(rows) <= MAX_STEPS, 'model rows')
        table = {}
        for row in rows:
            fields(row, ('args', 'value'), 'model row')
            args = row['args']
            require(type(args) is list and len(args) == len(spec['args']), 'model row arity')
            for arg, sort in zip(args, spec['args']):
                index(arg, domains[sort], 'model argument')
            key = tuple(args)
            require(key not in table, 'duplicate model tuple')
            table[key] = index(row['value'], domains[spec['result']], 'model result')
        tables[op] = table
    values = []
    for op, args in inp.nodes:
        values.append(tables[op].get(tuple(values[a] for a in args), defaults[op]))
    for a, b in inp.equations:
        if max(inp.depths[a], inp.depths[b]) <= horizon:
            require(values[a] == values[b], 'model violates active input equation')
    return values


def check(request, certificate):
    inp = parse(request)
    certificate = json.loads(canonical(certificate))
    fields(certificate, ('schema', 'request_sha256', 'mode', 'horizon', 'events', 'models', 'goals'), 'certificate')
    require(certificate['schema'] == PROOF_SCHEMA, 'certificate schema')
    require(certificate['request_sha256'] == inp.identity, 'certificate request binding')
    mode, horizon = certificate['mode'], certificate['horizon']
    require(type(mode) is str and mode in ('entailment', 'exact_threshold'), 'certificate mode')
    require(type(horizon) is int and 0 <= horizon <= inp.horizon, 'certificate horizon')
    require(all(max(inp.depths[a], inp.depths[b]) <= horizon for a, b in inp.queries), 'inactive query')
    events, models, goals = certificate['events'], certificate['models'], certificate['goals']
    require(type(events) is list and len(events) <= MAX_STEPS, 'proof event budget')
    require(type(models) is list and len(models) <= inp.horizon + 1, 'model budget')
    require(type(goals) is list and len(goals) == len(inp.queries), 'complete ordered goals required')
    established = []

    def path(a, b, ids, limit):
        require(type(ids) is list and len(ids) <= MAX_STEPS, 'proof path')
        current, cost = a, max(inp.depths[a], inp.depths[b])
        for eid in ids:
            index(eid, limit, 'chronologically earlier premise')
            x, y, depth = established[eid]
            require(current == x or current == y, 'disconnected proof path')
            current = y if current == x else x
            cost = max(cost, depth)
        require(current == b, 'proof path does not establish endpoints')
        return cost

    for i, event in enumerate(events):
        require(type(event) is dict and type(event.get('rule')) is str, 'proof rule')
        rule = event['rule']
        require(rule in ('axiom', 'congruence'), 'unknown proof rule')
        keys = ('rule', 'left', 'right', 'depth', 'equation' if rule == 'axiom' else 'premises')
        fields(event, keys, 'event')
        a, b = (index(event[k], len(inp.nodes), 'event endpoint') for k in ('left', 'right'))
        require(inp.node_sorts[a] == inp.node_sorts[b], 'ill-sorted proof event')
        cost = max(inp.depths[a], inp.depths[b])
        if rule == 'axiom':
            pair = inp.equations[index(event['equation'], len(inp.equations), 'actual axiom')]
            require((a, b) == pair or (b, a) == pair, 'event is not the cited input equation')
        else:
            op, args = inp.nodes[a]
            other_op, other_args = inp.nodes[b]
            require(op == other_op and len(args) == len(other_args), 'congruence head/arity')
            premises = event['premises']
            require(type(premises) is list and len(premises) == len(args), 'all congruence arguments required')
            for x, y, ids in zip(args, other_args, premises):
                cost = max(cost, path(x, y, ids, i))
        require(type(event['depth']) is int and event['depth'] == cost <= horizon, 'actual proof depth')
        established.append((a, b, cost))

    model_values, model_depths = [], []
    for model in models:
        require(type(model) is dict and type(model.get('horizon')) is int, 'model horizon type')
        d = model['horizon']
        require(0 <= d <= horizon and d not in model_depths, 'duplicate/out-of-range model horizon')
        model_values.append(check_model(inp, model, d))
        model_depths.append(d)

    def separates(mid, a, b, d):
        index(mid, len(models), 'model reference')
        require(model_depths[mid] == d, 'wrong lower/final model horizon')
        require(max(inp.depths[a], inp.depths[b]) <= d, 'model separates inactive query')
        require(model_values[mid][a] != model_values[mid][b], 'model does not separate query')

    results = []
    for (a, b), goal in zip(inp.queries, goals):
        require(type(goal) is dict and type(goal.get('status')) is str, 'goal status')
        status = goal['status']
        if status == 'equal':
            fields(goal, ('status', 'path', 'depth', 'lower_model'), 'equal goal')
            cost = path(a, b, goal['path'], len(events))
            require(type(goal['depth']) is int and goal['depth'] == cost <= horizon, 'goal proof depth')
            if mode == 'exact_threshold' and cost > max(inp.depths[a], inp.depths[b]):
                separates(goal['lower_model'], a, b, cost - 1)
            else:
                require(goal['lower_model'] is None, 'unexpected lower model')
            results.append({'status': 'equal', 'proof_depth': cost,
                            'exact_threshold': cost if mode == 'exact_threshold' else None})
        else:
            expected = 'not_entailed' if horizon == inp.horizon else 'not_visible'
            require(status == expected, 'bounded model cannot claim final nonconsequence')
            fields(goal, ('status', 'model'), 'separated goal')
            separates(goal['model'], a, b, horizon)
            results.append({'status': status, 'separation_horizon': horizon})
    return {'schema': 'qkf-ground-query-checked-v1', 'request_sha256': inp.identity,
            'mode': mode, 'horizon': horizon, 'final_horizon': inp.horizon, 'goals': results}
