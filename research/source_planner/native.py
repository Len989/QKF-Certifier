"""Invoke exactly one paid PR41 native rule; no target verdict is assumed."""
from research.source_query.rules import (input_bridge, mask_implication, parity_evidence,
                                       local_rhs, guard_truth, check_fact)


def derive(ctx, graph, candidate):
    rule = candidate['rule']
    fact = dict(candidate)
    if rule == 'input-bridge':
        pair = input_bridge(ctx, graph, candidate['atom'])
    elif rule == 'eq-mask':
        pair = mask_implication(ctx, graph, candidate['antecedent'], candidate['consequent'])
    elif rule == 'low-bit':
        rows = parity_evidence(ctx, candidate['masked_node'])
        if rows is None:
            return None
        fact['rows'] = rows
        pair = check_fact(ctx, graph, fact)
    elif rule == 'guard-zero':
        if not ctx.domain or not all(c == 0 for c, _ in ctx.domain):
            return None
        pair = check_fact(ctx, graph, fact)
    elif rule == 'guard-truth':
        pair = guard_truth(ctx, graph, candidate['term'])
    elif rule == 'local':
        value = local_rhs(ctx, graph, candidate['term'])
        if value is None:
            return None
        fact['law'] = value[0]
        pair = candidate['term'], value[1]
    else:
        raise ValueError('unknown native question')
    return None if pair is None else (fact, pair)
