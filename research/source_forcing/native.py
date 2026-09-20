"""Producer-only source facts, with complete paid branch dependencies."""
import itertools
from .context import PHASES, SEEDS, legacy, need, operator_name


def explain_branch(program, phase, m, a, g):
    inc, carry = phase
    total = g + carry
    bit, carry = total & 1, total >> 1
    steps = []

    def record(kind, action):
        steps.append(dict(rule=kind, action=action, state=[inc, bit, carry]))

    if inc:
        if m and not bit:
            action = program['mandatory_action']
            need(action in ('add', 'or'), 'mandatory source action')
            bit = 1
            record('mandatory', action)
        if not a and bit:
            action = program['forbidden_action']
            need(action == 'add', 'forbidden source action')
            carry += 1
            bit = 0
            record('forbidden', action)
    elif a and not m:
        action = program['first_action']
        if action == 'add':
            carry += bit
            bit ^= 1
        else:
            need(action == 'or', 'first source action')
            bit = 1
        inc = True
        record('first', action)
    need((inc, carry) in PHASES, 'physical phase closure')
    return dict(total=total, steps=steps, result=[bit, PHASES.index((inc, carry))])


def branches(ctx):
    _, kernel = legacy()
    m, a, g, _ = ctx['request']['label']
    result = []
    for i, phase in enumerate(PHASES):
        bit, next_phase = kernel.source_cell(ctx['program'], phase, m, a, g)
        proof = explain_branch(ctx['program'], phase, m, a, g)
        need(proof['result'] == [bit, PHASES.index(next_phase)], 'branch proof disagrees with retained source_cell')
        result.append(dict(phase=i, **proof))
    return result


def native_seed(ctx, proofs, target):
    y = ctx['request']['label'][3]
    out = 0
    for phase, proof in enumerate(proofs):
        bit, nxt = proof['result']
        if bit == y and target & (1 << nxt):
            out |= 1 << phase
    return dict(input=target, output=out, branches=[0, 1, 2])


def build_entry(a, b, operation):
    return a | b if operation == 'union' else a & b


def presentation(ctx, seeds):
    from research.pure_rows.common import INPUT, THEORY
    return dict(schema=INPUT, theory=THEORY,
                carrier=dict(names=[str(i) for i in range(8)], operations=[
                    dict(name=op, arity=2, table=[build_entry(a, b, op) for a in range(8) for b in range(8)])
                    for op in ('union', 'intersection')]),
                operators=dict(names=[operator_name(ctx)], operations=[]),
                cells=[[0, s['input'], s['output']] for s in seeds])


def compatibility():
    return dict(rule='guarded-deterministic-inverse-image-v1', phases=[list(p) for p in PHASES],
                boolean_rows=[[k, a, b, k & (a | b), (k & a) | (k & b),
                               k & (a & b), (k & a) & (k & b)]
                              for k, a, b in itertools.product((0, 1), repeat=3)])
