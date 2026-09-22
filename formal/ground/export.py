"""Deterministic ground JSON → Lean data, with an explicit positive projection.

No proof search and no conclusion-to-axiom conversion occurs here. The normal
entry point independently checks the original complete Python certificate.
``decoded_data`` also accepts semantically invalid shapes so the negative Lean
controls can exercise Lean's checker, rather than merely fail in Python.
"""
import argparse
import json
from pathlib import Path
import re

from research.ground_query.checker import check
from research.ground_query.schema import canonical, digest, fields, load_json, require


def natural(value):
    require(type(value) is int and 0 <= value < 2**31, 'bounded natural required')
    return value


def decoded_data(request, certificate):
    """Structural adapter; logical acceptance is determined separately."""
    request = json.loads(canonical(request))
    certificate = json.loads(canonical(certificate))
    fields(request, ('schema', 'sorts', 'signature', 'nodes', 'equations', 'queries'), 'input')
    fields(certificate, ('schema', 'request_sha256', 'mode', 'horizon', 'events', 'models', 'goals'), 'proof')
    require(request['schema'] == 'qkf-ground-query-input-v1', 'input schema')
    require(certificate['schema'] == 'qkf-ground-query-certificate-v1', 'proof schema')
    require(certificate['mode'] in ('entailment', 'exact_threshold'), 'proof mode')
    require(certificate['request_sha256'] == digest(request), 'request binding')
    sorts = {name: i for i, name in enumerate(request['sorts'])}
    require(len(sorts) == len(request['sorts']), 'duplicate sort')
    symbols = {name: i for i, name in enumerate(sorted(request['signature']))}
    signature = []
    for name in symbols:
        spec = request['signature'][name]
        fields(spec, ('args', 'result'), 'symbol')
        signature.append({'args': [sorts[s] for s in spec['args']], 'result': sorts[spec['result']]})
    nodes = []
    for node in request['nodes']:
        fields(node, ('op', 'args'), 'node')
        nodes.append({'op': symbols[node['op']], 'args': [natural(a) for a in node['args']]})

    def pair(p):
        require(type(p) is list and len(p) == 2, 'pair')
        return [natural(a) for a in p]

    events = []
    for event in certificate['events']:
        rule = event['rule']
        require(rule in ('axiom', 'congruence'), 'unsupported proof rule')
        fields(event, ('left', 'right', 'depth', 'rule',
                       'equation' if rule == 'axiom' else 'premises'), 'event')
        out = {key: natural(event[key]) for key in ('left', 'right', 'depth')}
        out['rule'] = rule
        if rule == 'axiom':
            out['equation'] = natural(event['equation'])
        else:
            out['premises'] = [[natural(i) for i in ids] for ids in event['premises']]
        events.append(out)
    require(len(certificate['goals']) == len(request['queries']), 'complete ordered goals')
    queries, goals, indices = [], [], []
    for i, (q, goal) in enumerate(zip(request['queries'], certificate['goals'])):
        require(goal['status'] in ('equal', 'not_entailed', 'not_visible'), 'goal status')
        if goal['status'] == 'equal':
            fields(goal, ('status', 'path', 'depth', 'lower_model'), 'equal goal')
            queries.append(pair(q))
            goals.append({'path': [natural(e) for e in goal['path']], 'depth': natural(goal['depth'])})
            indices.append(i)
    return {
        'request': {'sorts': len(sorts), 'signature': signature, 'nodes': nodes,
                    'equations': [pair(p) for p in request['equations']], 'queries': queries},
        'certificate': {'horizon': natural(certificate['horizon']), 'events': events, 'goals': goals},
        'binding': {'request_sha256': digest(request), 'certificate_sha256': digest(certificate),
                    'sort_ids': sorts, 'symbol_ids': symbols, 'positive_query_indices': indices,
                    'excluded_query_indices': [i for i in range(len(certificate['goals'])) if i not in indices],
                    'projection': 'positive equalities only; no lower-model or minimal-depth theorem'}
    }


def lean_list(items):
    return '[' + ', '.join(items) + ']'


def n(value):
    return str(natural(value))


def ns(values):
    return lean_list(n(i) for i in values)


def render(name, data, accepted=True):
    require(type(name) is str and re.fullmatch(r'[a-z][a-z0-9_]*', name), 'Lean identifier')
    req, cert = data['request'], data['certificate']
    signature = lean_list('⟨' + ns(s['args']) + ', ' + n(s['result']) + '⟩' for s in req['signature'])
    nodes = lean_list('⟨' + n(s['op']) + ', ' + ns(s['args']) + '⟩' for s in req['nodes'])
    pairs = lambda ps: lean_list('(' + n(a) + ', ' + n(b) + ')' for a, b in ps)
    events = []
    for e in cert['events']:
        if e['rule'] == 'axiom':
            rule = '.axiom ' + n(e['equation'])
        elif e['rule'] == 'congruence':
            rule = '.congruence ' + lean_list(ns(p) for p in e['premises'])
        else:
            raise ValueError('unknown event rule')
        events.append('⟨' + ', '.join([n(e['left']), n(e['right']), n(e['depth']), rule]) + '⟩')
    goals = lean_list('⟨' + ns(g['path']) + ', ' + n(g['depth']) + '⟩' for g in cert['goals'])
    expected = 'true' if accepted else 'false'
    return (f'def {name}_request : Request :=\n'
            f'  ⟨{n(req["sorts"])}, {signature},\n   {nodes},\n   {pairs(req["equations"])}, {pairs(req["queries"])}⟩\n'
            f'def {name}_certificate : Certificate :=\n'
            f'  ⟨{n(cert["horizon"])},\n   {lean_list(events)},\n   {goals}⟩\n'
            f'theorem {name}_{"accepted" if accepted else "rejected"} :\n'
            f'    checkRaw {name}_request {name}_certificate = {expected} := by decide +kernel\n')


def export(request, certificate, name):
    check(request, certificate)
    data = decoded_data(request, certificate)
    require(bool(data['certificate']['goals']) or not request['queries'], 'no positive goal to export')
    return data, render(name, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request', type=Path)
    parser.add_argument('certificate', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--name', default='exported')
    args = parser.parse_args()
    data, text = export(load_json(args.request), load_json(args.certificate), args.name)
    args.output.write_text('import Ground\nopen QKFGround\n' + text, encoding='utf-8')
    print(json.dumps(data['binding'], sort_keys=True))


if __name__ == '__main__':
    main()
