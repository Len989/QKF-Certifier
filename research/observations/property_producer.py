"""Derive closure of the joint source and specification observations."""
from .model import integer, require
from .property_kernel import MAX_STATES, MAX_WITNESS, SCHEMA, System
from .upper_spec import decode


def synthesize(source, source_certificate, spec, *, max_states=MAX_STATES):
    require(integer(max_states, 1, MAX_STATES), 'property producer state budget')
    system = System(source, source_certificate, spec)
    states = [system.initial]; ids = {system.initial: 0}; parents = [None]
    for i, state in enumerate(states):
        reason = system.bad(state)
        if reason is not None:
            word = []; cursor = i
            while parents[cursor] is not None:
                cursor, column = parents[cursor]; word.append(column)
            word.reverse()
            if not word or len(word) > MAX_WITNESS:
                return {'status': 'budget_exhausted', 'reason': 'counterexample length budget', 'certificate': None}
            return {'status': 'candidate', 'certificate': {
                'schema': SCHEMA, 'kind': 'counterexample', 'binding': system.binding,
                'word': word, 'values': decode(word), 'reason': reason}}
        for column in system.alphabet:
            nxt = system.advance(state, column)
            if nxt not in ids:
                if len(states) == max_states:
                    return {'status': 'budget_exhausted', 'reason': 'joint observation state budget', 'certificate': None}
                ids[nxt] = len(states); states.append(nxt); parents.append([i, column])
    return {'status': 'candidate', 'certificate': {
        'schema': SCHEMA, 'kind': 'closed_observation', 'binding': system.binding,
        'states': [{'state': list(s), 'parent': p} for s, p in zip(states, parents)]}}
