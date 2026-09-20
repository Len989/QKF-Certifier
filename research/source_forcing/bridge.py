"""Independent source-cell proof replay and concrete-to-pure-row soundness bridge.

Does not import native fact generation, any producer, or call source_cell.
"""
import itertools
from .context import PHASES, SEEDS, encoded, fields, integer, need, operator_name


def verify_branch(ctx, proof, phase):
    fields(proof, ('phase', 'total', 'steps', 'result'))
    need(type(proof['phase']) is int and proof['phase'] == phase, 'ordered physical branch')
    inc, carry = PHASES[phase]
    m, a, g, _ = ctx['request']['label']
    integer(proof['total'], 0, 2)
    need(proof['total'] == g + carry, 'incoming physical addition')
    bit, carry = proof['total'] % 2, proof['total'] // 2
    steps = proof['steps']
    need(type(steps) is list and len(steps) <= 2, 'branch step bound')
    consumed = 0

    def apply(kind):
        nonlocal bit, carry, inc, consumed
        need(consumed < len(steps), 'omitted source repair')
        step = steps[consumed]
        fields(step, ('rule', 'action', 'state'))
        action = ctx['program'][kind + '_action']
        need(step['rule'] == kind and step['action'] == action, 'repair instruction/source binding')
        if kind == 'mandatory':
            need(action in ('or', 'add') and bit == 0, 'mandatory repair semantics')
            bit = 1
        elif kind == 'forbidden':
            need(action == 'add' and bit == 1, 'forbidden repair semantics')
            bit = 0
            carry += 1
        else:
            need(kind == 'first' and action in ('add', 'or'), 'first repair semantics')
            if action == 'add':
                carry, bit = carry + bit, 1 - bit
            else:
                bit = 1
            inc = True
        need(encoded(step['state']) == encoded([inc, bit, carry]), 'false intermediate source state')
        consumed += 1

    if inc:
        if m and bit == 0:
            apply('mandatory')
        if a == 0 and bit == 1:
            apply('forbidden')
    elif a == 1 and m == 0:
        apply('first')
    need(consumed == len(steps), 'spurious or duplicate branch repair')
    need((inc, carry) in PHASES, 'source action leaves physical phase domain')
    actual = [bit, PHASES.index((inc, carry))]
    need(encoded(proof['result']) == encoded(actual), 'source output/continuation')
    return actual


def verify_seed(ctx, fact, target, transitions):
    fields(fact, ('input', 'output', 'branches'))
    need(type(fact['input']) is int and fact['input'] == target, 'seed input/order')
    integer(fact['output'], 0, 7)
    need(encoded(fact['branches']) == encoded([0, 1, 2]), 'complete seed source dependencies')
    wanted = ctx['request']['label'][3]
    for phase, (bit, nxt) in enumerate(transitions):
        membership = bit == wanted and bool(target & (1 << nxt))
        need(bool(fact['output'] & (1 << phase)) == membership, 'false native seed membership')
    return fact['output']


def check_boolean_row(row, k, a, b):
    expected = [k, a, b, k & (a | b), (k & a) | (k & b), k & (a & b), (k & a) & (k & b)]
    need(encoded(row) == encoded(expected), 'pointwise inverse-image compatibility')
    need(row[3] == row[4] and row[5] == row[6], 'union/intersection distributivity')


def verify_compatibility(proof):
    fields(proof, ('rule', 'phases', 'boolean_rows'))
    need(proof['rule'] == 'guarded-deterministic-inverse-image-v1', 'compatibility rule')
    need(encoded(proof['phases']) == encoded([list(p) for p in PHASES]), 'physical phase labels')
    rows = proof['boolean_rows']
    need(type(rows) is list and len(rows) == 8, 'complete pointwise Boolean cases')
    for row, (k, a, b) in zip(rows, itertools.product((0, 1), repeat=3)):
        check_boolean_row(row, k, a, b)


def verify_preparation(ctx, proof, with_seeds):
    fields(proof, ('branches', 'seeds', 'compatibility'))
    need(type(proof['branches']) is list and len(proof['branches']) == 3, 'all physical phases required')
    transitions = [verify_branch(ctx, p, i) for i, p in enumerate(proof['branches'])]
    seeds = proof['seeds']
    need(type(seeds) is list and len(seeds) == (4 if with_seeds else 0), 'seed count')
    values = {target: verify_seed(ctx, fact, target, transitions) for target, fact in zip(SEEDS, seeds)}
    if with_seeds:
        # The checked source is a deterministic phase-closed function. For each
        # q, k=[out(q)=y], a=[next(q) in P], b=[next(q) in R]. These eight
        # Boolean identities prove compatibility for ALL P,R without an h table.
        verify_compatibility(proof['compatibility'])
    else:
        need(proof['compatibility'] is None, 'direct cell has no algebra preparation')
    return transitions, values


def check_entry(given, a, b, union):
    need(type(given) is int and given == (a | b if union else a & b), 'native table disagrees with concrete subsets')


def verify_presentation(ctx, raw, seeds):
    from research.pure_rows.common import presentation
    p = presentation(raw)
    need(p['carrier']['names'] == [str(i) for i in range(8)], 'concrete subset labels')
    need(p['operators'] == dict(names=[operator_name(ctx)], operations=[]), 'actual source action label')
    ops = p['carrier']['operations']
    need(len(ops) == 2, 'union/intersection signature only')
    for op, name in zip(ops, ('union', 'intersection')):
        need(op['name'] == name and op['arity'] == 2, 'native operation meaning')
        for a in range(8):
            for b in range(8):
                check_entry(op['table'][a * 8 + b], a, b, name == 'union')
    need(p['cells'] == [[0, a, seeds[a]] for a in SEEDS], 'pure-row cells must be exactly checked source seeds')
    return p


def verify_descent(proof, result):
    fields(proof, ('rule', 'carrier_partition'))
    diagonal = [[i] for i in range(8)]
    need(proof['rule'] == 'identity-on-physical-powerset' and
         encoded(proof['carrier_partition']) == encoded(diagonal), 'only identity descent is admitted')
    need(result['carrier_protected'] and result['carrier_partition'] == diagonal,
         'a quotient cannot repair distinguishable concrete source observations')
