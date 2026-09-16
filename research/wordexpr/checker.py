"""Source-bound replay with the existing QKF forced-row checker; no search import."""
from research.observations.checker import check as check_observations
from research.observations.model import digest, integer, require

from .frontend import CONTRACT, goal, read_source
from .semantics import cell, evaluate, goal_cell, goal_initial, goal_value, initial, model, valid_state

SCHEMA = 'qkf-word-expression-certificate-v1'
SOURCE_SCHEMA = 'qkf-word-expression-source-v1'
MAX_STATES = 64
MAX_PRODUCT = 4096


def check_source(source, entry, cert):
    require(type(cert) is dict and set(cert) == {'schema', 'ir', 'carrier', 'observations'} and
            cert['schema'] == SOURCE_SCHEMA, 'source certificate fields')
    ir = read_source(source, entry)
    require(digest(cert['ir']) == digest(ir), 'exact external source/entry binding')
    records = cert['carrier']
    require(type(records) is list and 0 < len(records) <= MAX_STATES, 'source carrier budget')
    states = []
    for i, r in enumerate(records):
        require(type(r) is dict and set(r) == {'state', 'parent'}, 'source record fields')
        s = valid_state(ir, r['state'])
        require(s not in states, 'distinct source states')
        p = r['parent']
        if i == 0:
            require(p is None and s == initial(ir), 'actual source initial state')
        else:
            require(type(p) is list and len(p) == 2 and integer(p[0], 0, i - 1), 'earlier source parent')
            require(cell(ir, states[p[0]], p[1])[1] == s, 'source reachability derivation')
        states.append(s)
    data = model(ir, states)  # Recomputes all source cells; checks closure.
    checked = check_observations(data, cert['observations'])
    return ir, checked


def prepare(source, spec, source_cert):
    target = goal(spec)
    ir, result = check_source(source, spec['entry'], source_cert)
    obs = source_cert['observations']
    table = {(r['state'], r['symbol']): (r['output'], r['next']) for r in obs['cells']}
    start = (obs['initial'], *goal_initial(target))
    return ir, target, result, table, start


def joint_step(target, table, state, a):
    y, q = table[state[0], a]
    expected, residual = goal_cell(target, state[1:], a)
    return y, expected, (q, *residual)


def check(source, spec, cert):
    require(type(cert) is dict and set(cert) == {'schema', 'goal_sha256', 'source', 'proof'} and
            cert['schema'] == SCHEMA, 'certificate fields')
    require(cert['goal_sha256'] == digest(spec), 'independent external goal binding')
    ir, target, source_result, table, start = prepare(source, spec, cert['source'])
    proof = cert['proof']
    require(type(proof) is dict and type(proof.get('kind')) is str, 'property proof')
    base = {'contract': CONTRACT, 'entry': spec['entry'], 'goal_sha256': digest(spec),
            'source_sha256': ir['source_sha256'], 'source': source_result,
            'trust': 'restricted lexical frontend, modular cut rules and positional goal semantics; not Lean-verified'}
    if proof['kind'] == 'closure':
        require(set(proof) == {'kind', 'states'}, 'positive proof fields')
        records, states = proof['states'], []
        require(type(records) is list and 0 < len(records) <= MAX_PRODUCT, 'property carrier budget')
        for i, r in enumerate(records):
            require(type(r) is dict and set(r) == {'state', 'parent'}, 'property state record')
            state = r['state']
            require(type(state) is list and state and integer(state[0], 0, source_result['classes'] - 1),
                    'property source class')
            if target is None:
                require(len(state) == 2 and integer(state[1], 0, 1), 'first-one observation')
            else:
                valid_state(target, state[1:])
            s = tuple(state)
            require(s not in states, 'distinct property states')
            p = r['parent']
            if i == 0:
                require(p is None and s == start, 'property initial state')
            else:
                require(type(p) is list and len(p) == 2 and integer(p[0], 0, i - 1) and
                        type(p[1]) is str and p[1] in {'0', '1'}, 'property parent')
                require(joint_step(target, table, states[p[0]], p[1])[2] == s, 'property reachability')
            states.append(s)
        known = set(states)
        for s in states:
            for a in ('0', '1'):
                actual, expected, nxt = joint_step(target, table, s, a)
                require(actual == expected, 'violated independent output obligation')
                require(nxt in known, 'property carrier not closed under both bits')
        return {**base, 'status': 'certified', 'all_positive_widths': True,
                'product_states': len(states), 'checked_edges': 2 * len(states)}
    require(proof['kind'] == 'counterexample' and set(proof) == {'kind', 'bits', 'input', 'output', 'expected'},
            'negative proof fields')
    bits = proof['bits']
    require(type(bits) is str and 0 < len(bits) <= 4096 and set(bits) <= {'0', '1'}, 'positive witness width')
    width, x = len(bits), sum(int(a) << k for k, a in enumerate(bits))
    q, y = start[0], 0
    for k, a in enumerate(bits):
        out, q = table[q, a]
        y |= int(out) << k
    expected = goal_value(target, x, width)
    require(y == evaluate(ir, x, width), 'source factor versus independent whole-word interpreter')
    require(all(integer(proof[k], 0, (1 << width) - 1) for k in ('input', 'output', 'expected')),
            'witness numbers')
    require((proof['input'], proof['output'], proof['expected']) == (x, y, expected) and y != expected,
            'actual numerical goal violation required')
    return {**base, 'status': 'refuted', 'all_positive_widths': False,
            'width': width, 'input': x, 'output': y, 'expected': expected}
