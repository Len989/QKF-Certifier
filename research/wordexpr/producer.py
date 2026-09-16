"""Propose generic arithmetic carriers, existing QKF factors and target closures."""
from research.observations.model import digest, integer, require
from research.observations.producer import synthesize

from .checker import MAX_PRODUCT, MAX_STATES, SCHEMA, SOURCE_SCHEMA, check, joint_step, prepare
from .frontend import goal, read_source
from .semantics import cell, evaluate, goal_value, initial, model


class Budget(ValueError):
    pass


def derive(source, spec, *, max_states=MAX_STATES, max_product=MAX_PRODUCT):
    goal(spec)
    require(integer(max_states, 1, MAX_STATES) and integer(max_product, 1, MAX_PRODUCT), 'producer budgets')
    ir = read_source(source, spec['entry'])
    start = initial(ir)
    states, records = [start], [{'state': list(start), 'parent': None}]
    ids = {start: 0}
    for i, s in enumerate(states):
        for a in ('0', '1'):
            nxt = cell(ir, s, a)[1]
            if nxt not in ids:
                if len(states) == max_states:
                    raise Budget('source residual-state budget')
                ids[nxt] = len(states)
                states.append(nxt)
                records.append({'state': list(nxt), 'parent': [i, a]})
    proposed = synthesize(model(ir, states), row_encoding='atomic')
    if proposed['status'] != 'candidate':
        raise Budget('QKF observation budget: ' + proposed['reason'])
    source_cert = {'schema': SOURCE_SCHEMA, 'ir': ir, 'carrier': records, 'observations': proposed['certificate']}
    ir, target, _, table, start = prepare(source, spec, source_cert)
    states, paths = [start], ['']
    records, ids = [{'state': list(start), 'parent': None}], {start: 0}
    proof = None
    for i, s in enumerate(states):
        for a in ('0', '1'):
            actual, expected, nxt = joint_step(target, table, s, a)
            bits = paths[i] + a
            if actual != expected:
                x = sum(int(b) << k for k, b in enumerate(bits))
                proof = {'kind': 'counterexample', 'bits': bits, 'input': x,
                         'output': evaluate(ir, x, len(bits)), 'expected': goal_value(target, x, len(bits))}
                break
            if nxt not in ids:
                if len(states) == max_product:
                    raise Budget('joint target-state budget')
                ids[nxt] = len(states)
                states.append(nxt)
                paths.append(bits)
                records.append({'state': list(nxt), 'parent': [i, a]})
        if proof is not None:
            break
    if proof is None:
        proof = {'kind': 'closure', 'states': records}
    cert = {'schema': SCHEMA, 'goal_sha256': digest(spec), 'source': source_cert, 'proof': proof}
    return cert, check(source, spec, cert)
