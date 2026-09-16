"""Propose a residual carrier and terminal product; always independently replay."""
from research.observations.model import digest, integer, require
from research.observations.producer import synthesize
from .checker import MAX_PRODUCT, MAX_STATES
from .producer import Budget
from .predicate_checker import SCHEMA, SOURCE_SCHEMA, check, joint_step, prepare
from .predicate_frontend import goal, read_source, target_value
from .predicate_semantics import cell, evaluate, initial, model


def derive(source, spec, *, max_states=MAX_STATES, max_product=MAX_PRODUCT):
    goal(spec)
    require(integer(max_states, 1, MAX_STATES) and integer(max_product, 1, MAX_PRODUCT), 'predicate budgets')
    ir = read_source(source, spec['entry'], spec['word_type'])
    start = initial(ir)
    states, rows, ids = [start], [{'state': list(start), 'parent': None}], {start: 0}
    for i, s in enumerate(states):
        for a in ('0', '1'):
            nxt = cell(ir, s, a)
            if nxt not in ids:
                if len(states) == max_states:
                    raise Budget('predicate arithmetic/inequality state budget')
                ids[nxt] = len(states)
                states.append(nxt)
                rows.append({'state': list(nxt), 'parent': [i, a]})
    proposed = synthesize(model(ir, states), row_encoding='atomic')
    if proposed['status'] != 'candidate':
        raise Budget('predicate QKF budget: ' + proposed['reason'])
    source_cert = {'schema': SOURCE_SCHEMA, 'ir': ir, 'carrier': rows, 'observations': proposed['certificate']}
    limit, ir, _, table, terminals, start = prepare(source, spec, source_cert)
    states, rows, ids, paths = [start], [{'state': list(start), 'parent': None}], {start: 0}, ['']
    proof = None
    for i, s in enumerate(states):
        for a in ('0', '1'):
            nxt, bits = joint_step(table, limit, s, a), paths[i] + a
            if terminals[nxt[0]] != target_value(spec['target'], nxt[1]):
                x = sum(int(b) << k for k, b in enumerate(bits))
                proof = {'kind': 'counterexample', 'bits': bits, 'input': x,
                         'output': evaluate(ir, x, len(bits)),
                         'expected': target_value(spec['target'], x.bit_count())}
                break
            if nxt not in ids:
                if len(states) == max_product:
                    raise Budget('predicate target product budget')
                ids[nxt] = len(states)
                states.append(nxt)
                paths.append(bits)
                rows.append({'state': list(nxt), 'parent': [i, a]})
        if proof is not None:
            break
    if proof is None:
        proof = {'kind': 'closure', 'states': rows}
    cert = {'schema': SCHEMA, 'goal_sha256': digest(spec), 'source': source_cert, 'proof': proof}
    return cert, check(source, spec, cert)
