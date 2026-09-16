"""Independent terminal-property replay. No producer/search imports."""
from research.observations.checker import check as check_observations
from research.observations.model import digest, integer, require
from .checker import MAX_PRODUCT, MAX_STATES
from .predicate_frontend import CONTRACT, goal, read_source, target_value
from .predicate_semantics import cell, evaluate, initial, model, valid_state

SCHEMA = 'qkf-word-predicate-certificate-v1'
SOURCE_SCHEMA = 'qkf-word-predicate-source-v1'


def check_source(source, spec, cert):
    require(type(cert) is dict and set(cert) == {'schema', 'ir', 'carrier', 'observations'} and
            cert['schema'] == SOURCE_SCHEMA, 'predicate source fields')
    ir = read_source(source, spec['entry'], spec['word_type'])
    require(digest(ir) == digest(cert['ir']), 'exact predicate source/entry/type binding')
    records = cert['carrier']
    require(type(records) is list and 0 < len(records) <= MAX_STATES, 'source carrier budget')
    states = []
    for i, r in enumerate(records):
        require(type(r) is dict and set(r) == {'state', 'parent'}, 'source record fields')
        s = valid_state(ir, r['state'])
        require(s not in states, 'distinct predicate source states')
        p = r['parent']
        if i == 0:
            require(p is None and s == initial(ir), 'actual source initial state')
        else:
            require(type(p) is list and len(p) == 2 and integer(p[0], 0, i - 1), 'earlier source parent')
            require(cell(ir, states[p[0]], p[1]) == s, 'predicate source reachability')
        states.append(s)
    data = model(ir, states)
    checked = check_observations(data, cert['observations'])
    obs = cert['observations']
    table = {(r['state'], r['symbol']): r['next'] for r in obs['cells']}
    # Existing QKF checker has checked equality of terminal labels in each block.
    terminals = {q: data['terminal'][block[0]] == 'true' for q, block in enumerate(obs['blocks'])}
    return ir, checked, table, terminals, (obs['initial'], 0)


def joint_step(table, limit, state, a):
    require(type(a) is str and a in {'0', '1'}, 'binary predicate column')
    return table[state[0], a], min(limit, state[1] + int(a))


def prepare(source, spec, source_cert):
    limit = goal(spec)
    return (limit, *check_source(source, spec, source_cert))


def check(source, spec, cert):
    require(type(cert) is dict and set(cert) == {'schema', 'goal_sha256', 'source', 'proof'} and
            cert['schema'] == SCHEMA, 'predicate certificate fields')
    require(cert['goal_sha256'] == digest(spec), 'independent predicate goal binding')
    limit, ir, checked, table, terminals, start = prepare(source, spec, cert['source'])
    base = {'contract': CONTRACT, 'entry': spec['entry'], 'word_type': spec['word_type'],
            'java_width': 32 if spec['word_type'] == 'int' else 64,
            'goal_sha256': digest(spec), 'source_sha256': ir['source_sha256'], 'source': checked,
            'trust': 'restricted typed lexical frontend; modular cut, equality and count rules; not Lean-verified'}
    proof = cert['proof']
    require(type(proof) is dict and proof.get('kind') in {'closure', 'counterexample'}, 'predicate proof')
    if proof['kind'] == 'closure':
        require(set(proof) == {'kind', 'states'}, 'positive predicate proof fields')
        rows, states = proof['states'], []
        require(type(rows) is list and 0 < len(rows) <= MAX_PRODUCT, 'predicate product budget')
        for i, r in enumerate(rows):
            require(type(r) is dict and set(r) == {'state', 'parent'}, 'predicate product record')
            s = r['state']
            require(type(s) is list and len(s) == 2 and integer(s[0], 0, checked['classes'] - 1)
                    and integer(s[1], 0, limit), 'typed count/source product')
            s = tuple(s)
            require(s not in states, 'distinct product states')
            p = r['parent']
            if i == 0:
                require(p is None and s == start, 'predicate product initial state')
            else:
                require(type(p) is list and len(p) == 2 and integer(p[0], 0, i - 1), 'earlier product parent')
                require(joint_step(table, limit, states[p[0]], p[1]) == s, 'predicate product reachability')
            states.append(s)
        known = set(states)
        for s in states:
            for a in ('0', '1'):
                nxt = joint_step(table, limit, s, a)
                require(nxt in known, 'predicate product closure')
                # Every edge ends a nonempty word, including a return to start.
                require(terminals[nxt[0]] == target_value(spec['target'], nxt[1]),
                        'violated terminal predicate obligation')
        return {**base, 'status': 'certified', 'all_positive_widths': True,
                'product_states': len(states), 'checked_edges': 2 * len(states)}
    require(set(proof) == {'kind', 'bits', 'input', 'output', 'expected'}, 'predicate witness fields')
    bits = proof['bits']
    require(type(bits) is str and 0 < len(bits) <= 4096 and set(bits) <= {'0', '1'}, 'positive witness width')
    width = len(bits)
    x = sum(int(a) << i for i, a in enumerate(bits))
    q = start[0]
    for a in bits:
        q = table[q, a]
    actual, expected = evaluate(ir, x, width), target_value(spec['target'], x.bit_count())
    require(actual == terminals[q], 'full-word evaluation and terminal factor agree')
    require(integer(proof['input'], 0, (1 << width) - 1) and
            type(proof['output']) is bool and type(proof['expected']) is bool, 'typed Boolean witness')
    require((proof['input'], proof['output'], proof['expected']) == (x, actual, expected)
            and actual != expected, 'actual predicate target violation')
    native_width = base['java_width']
    native_x = x & ((1 << native_width) - 1)
    native_actual = evaluate(ir, native_x, native_width)
    native_expected = target_value(spec['target'], native_x.bit_count())
    return {**base, 'status': 'refuted', 'all_positive_widths': False,
            'width': width, 'input': x, 'output': actual, 'expected': expected,
            'native_width_check': {'input': native_x, 'output': native_actual, 'expected': native_expected,
                                   'violates_goal': native_actual != native_expected,
                                   'kind': 'IR evaluation, not Java execution'}}
