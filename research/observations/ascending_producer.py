"""Discover residual arithmetic states, then use the existing QKF producer."""
from .ascending_kernel import ALPHABET, MAX_OFFSET, MAX_STATES, SCHEMA, cell, compiled_model
from .ascending_source import read_source
from .model import integer, require
from .producer import synthesize as observe


def synthesize(source, *, max_states=MAX_STATES, max_offset=MAX_OFFSET, **observation_budgets):
    require(integer(max_states, 1, MAX_STATES) and integer(max_offset, 0, MAX_OFFSET), 'residual budgets')
    ir = read_source(source); first = tuple(ir['register_initial']) + (0,)
    states = [first]; index = {first: 0}; records = [{'state': list(first), 'parent': None}]
    for i, state in enumerate(states):
        for a in ALPHABET:
            _, next_state = cell(ir, state, a)
            if next_state[-1] > max_offset or next_state not in index and len(states) == max_states:
                return {'status': 'budget_exhausted', 'stage': 'source_residuals',
                        'reason': 'residual offset or state budget', 'certificate': None}
            if next_state not in index:
                index[next_state] = len(states); states.append(next_state)
                records.append({'state': list(next_state), 'parent': [i, a]})
    result = observe(compiled_model(ir, states), row_encoding='atomic', **observation_budgets)
    if result['status'] != 'candidate': return {**result, 'stage': 'observations'}
    return {'status': 'candidate', 'certificate': {'schema': SCHEMA, 'source_ir': ir,
                                                  'carrier': records, 'observations': result['certificate']}}
