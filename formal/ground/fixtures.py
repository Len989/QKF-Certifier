"""Reproducible live-schema fixtures and semantic negative controls for PR50."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from research.ground_query.checker import check
from research.ground_query.fixtures import encode, examples, gap, shared_example, term, unary_signature
from research.ground_query.producer import prove
from research.ground_query.schema import canonical, digest
from .export import decoded_data, export, render

ROOT = Path(__file__).resolve().parent
PRODUCER_BASE = '55942faaeb253f19b849e9a52ea99cfd4b240a77'


def positives():
    request = gap()
    cert, _ = prove(request)
    yield 'gap', request, cert
    flattened = dict(examples())['flattened']
    old = deepcopy(cert)
    old['request_sha256'] = digest(flattened)
    yield 'flattened_nonminimal', flattened, old
    shared = shared_example()
    shared_cert, _ = prove(shared)
    yield 'shared_typed', shared, shared_cert
    a, b, c, d = [term(n) for n in ('a', 'b', 'c', 'd')]
    sig = {'a': {'args': [], 'result': 'A'}, 'c': {'args': [], 'result': 'A'},
           'b': {'args': [], 'result': 'B'}, 'd': {'args': [], 'result': 'B'},
           'f': {'args': ['A', 'B'], 'result': 'A'}}
    fa, fc = term('f', a, b), term('f', c, d)
    binary = encode(sig, [(a, c), (b, d)], [(fa, fc), (fc, fa)], ('A', 'B'))
    binary_cert, _ = prove(binary)
    yield 'typed_binary', binary, binary_cert
    reflexive = encode(unary_signature([a]), [], [(a, a)])
    reflexive_cert, _ = prove(reflexive)
    yield 'reflexive', reflexive, reflexive_cert
    reverse = deepcopy(cert)
    for event in reverse['events']:
        if event['rule'] == 'axiom':
            event['left'], event['right'] = event['right'], event['left']
    yield 'reverse_axioms', request, reverse
    active = encode(unary_signature([a, b, c, d]), [(a, b), (term('f', term('f', c)), d)], [(a, b)])
    active_cert, _ = prove(active, horizon=0)
    yield 'active_prefix', active, active_cert
    empty = dict(examples())['empty']
    empty_cert, _ = prove(empty)
    yield 'empty', empty, empty_cert
    chain = encode(unary_signature([a, b, c, d]), [(a, b), (b, c), (c, d)], [(a, d), (d, a)])
    chain_cert, _ = prove(chain)
    yield 'transitive_chain', chain, chain_cert


def negatives(cases):
    """Mutate serialized inputs, then require both independent checkers to reject.

    The unknown numeric symbol is a Lean-only decoded-boundary control: JSON
    names are mapped before Lean, so the Python adapter rejects unknown names.
    """
    gap_req, gap_cert = cases['gap']

    def changed(name, action, base='gap'):
        req, cert = deepcopy(cases[base])
        action(req, cert)
        cert['request_sha256'] = digest(req)
        try:
            check(req, cert)
        except (ValueError, KeyError, TypeError, IndexError):
            pass
        else:
            raise ValueError('negative Python control accepted: ' + name)
        return name, req, cert, decoded_data(req, cert)

    yield changed('node_self_reference', lambda r, c: r['nodes'][2].update(args=[2]))
    yield changed('node_forward_reference', lambda r, c: r['nodes'][2].update(args=[6]))
    yield changed('node_bad_reference', lambda r, c: r['nodes'][2].update(args=[999]))
    yield changed('node_wrong_arity', lambda r, c: r['nodes'][2].update(args=[]))
    yield changed('node_wrong_sort', lambda r, c: r['nodes'][4].update(args=[2, 2]), 'typed_binary')
    yield changed('equation_wrong_sort', lambda r, c: r['equations'][0].__setitem__(1, 2), 'typed_binary')
    yield changed('query_wrong_sort', lambda r, c: r['queries'][0].__setitem__(1, 2), 'typed_binary')
    yield changed('event_wrong_sort', lambda r, c: c['events'][0].update(right=2), 'typed_binary')
    yield changed('event_bad_endpoint', lambda r, c: c['events'][0].update(left=999))
    yield changed('substituted_axiom', lambda r, c: c['events'][0].update(equation=1))
    yield changed('axiom_bad_index', lambda r, c: c['events'][0].update(equation=999))
    yield changed('congruence_wrong_head', lambda r, c: c['events'][2].update(right=4))
    yield changed('missing_premise', lambda r, c: c['events'][2].update(premises=[]))
    yield changed('extra_premise', lambda r, c: c['events'][2]['premises'].append([]))
    yield changed('forward_event', lambda r, c: c['events'][2].update(premises=[[3]]))
    yield changed('self_event', lambda r, c: c['events'][2].update(premises=[[2]]))
    yield changed('bad_event_reference', lambda r, c: c['events'][2].update(premises=[[999]]))
    yield changed('broken_premise_path', lambda r, c: c['events'][2].update(premises=[[1]]))
    yield changed('broken_goal_path', lambda r, c: c['goals'][0].update(path=[]))
    yield changed('wrong_goal_depth', lambda r, c: c['goals'][0].update(depth=0))
    yield changed('wrong_event_depth', lambda r, c: c['events'][0].update(depth=0))
    yield changed('inactive_event', lambda r, c: c.update(horizon=1))
    yield changed('unused_bad_event', lambda r, c: c['events'].append(
        dict(c['events'][0], equation=1)))
    # Shape-valid Lean-only controls must not be blocked by the JSON adapter.
    for name, action in (
        ('unknown_numeric_head', lambda d: d['request']['nodes'][0].update(op=999)),
        ('missing_goal', lambda d: d['certificate'].update(goals=[])),
        ('extra_goal', lambda d: d['certificate']['goals'].append(deepcopy(d['certificate']['goals'][0]))),
        ('empty_sort_declaration', lambda d: d['request'].update(sorts=0)),
        ('out_of_range_sort', lambda d: d['request']['signature'][0].update(result=999)),
    ):
        data = decoded_data(gap_req, gap_cert)
        action(data)
        yield name, None, None, data


HEADER = ('import Ground\n\nset_option maxRecDepth 16384\n'
          'set_option maxHeartbeats 8000000\n\nnamespace QKFGround.Examples\n\n')


def expected_files():
    files, entries, pieces = {}, [], []
    cases = {}
    for name, request, cert in positives():
        cases[name] = (request, cert)
        data, lean = export(request, cert, name)
        for label, obj in (('request', request), ('certificate', cert), ('decoded', data)):
            files[f'evidence/{name}.{label}.json'] = canonical(obj) + b'\n'
        pieces.append(lean)
        entries.append({'name': name, 'expected': True, **data['binding'],
                        'nodes': len(request['nodes']), 'events': len(cert['events'])})
    negative_names = []
    for name, request, cert, data in negatives(cases):
        negative_names.append(name)
        prefix = 'reject_' + name
        pieces.append(render(prefix, data, accepted=False))
        files[f'evidence/{prefix}.decoded.json'] = canonical(data) + b'\n'
        if request is not None:
            files[f'evidence/{prefix}.request.json'] = canonical(request) + b'\n'
            files[f'evidence/{prefix}.certificate.json'] = canonical(cert) + b'\n'
        entries.append({'name': prefix, 'expected': False,
                        'python_rejected': request is not None, 'decoded_only': request is None})
    files['Examples.lean'] = (HEADER + '\n'.join(pieces) + '\nend QKFGround.Examples\n').encode()
    manifest = {'schema': 'qkf-ground-lean-fixtures-v1', 'producer_base': PRODUCER_BASE,
                'positive_count': len(cases), 'negative_count': len(negative_names), 'cases': entries,
                'files': {name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(files.items())}}
    files['FIXTURES.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    return files


def regenerate(check_only=False):
    files = expected_files()
    for name, raw in files.items():
        path = ROOT / name
        if check_only:
            if not path.is_file() or path.read_bytes() != raw:
                raise ValueError('fixture/export drift: ' + name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    actual = {p.relative_to(ROOT).as_posix() for p in (ROOT / 'evidence').glob('*') if p.is_file()}
    if actual != {p for p in files if p.startswith('evidence/')}:
        raise ValueError('unexpected fixture files')
    return json.loads(files['FIXTURES.json'])


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    result = regenerate(parser.parse_args().check)
    print(json.dumps({'positive': result['positive_count'], 'negative': result['negative_count']}, sort_keys=True))
