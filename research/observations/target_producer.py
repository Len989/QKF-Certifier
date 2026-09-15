"""Search a finite joint observation for any supported typed target formula.

Only the common System is used: there is no branch on a target name. Replaying
both positive and negative candidates is the independent checker's job.
"""
from .model import integer, require
from .target_kernel import MAX_STATES, MAX_WITNESS, SCHEMA, System


def synthesize(source, source_certificate, spec, *, max_states=MAX_STATES, max_witness=MAX_WITNESS):
    require(integer(max_states, 1, MAX_STATES) and integer(max_witness, 1, MAX_WITNESS),
            'typed target producer budgets')
    system = System(source, source_certificate, spec)
    states = [system.initial]
    nodes = [{'state': list(system.initial), 'parent': None}]
    seen = {system.initial}
    base = {'schema': SCHEMA, 'binding': system.binding, 'program': system.program}

    def exhausted(reason):
        return {'status': 'budget_exhausted', 'stage': 'typed_target', 'reason': reason,
                'explored_states': len(states), 'certificate': None}

    for i, state in enumerate(states):
        for column in system.alphabet:
            following = system.advance(state, column)
            reason = system.bad(following)
            if reason is not None:
                word, ancestor = [column], i
                while nodes[ancestor]['parent'] is not None:
                    ancestor, previous = nodes[ancestor]['parent']
                    word.append(previous)
                word.reverse()
                if len(word) > max_witness:
                    return exhausted('counterexample length budget')
                _, values = system.trace(word)
                return {'status': 'candidate', 'certificate': {
                    **base, 'kind': 'counterexample', 'word': word, 'values': values, 'reason': reason}}
            if following not in seen:
                if len(states) == max_states:
                    return exhausted('joint observation state budget')
                seen.add(following)
                states.append(following)
                nodes.append({'state': list(following), 'parent': [i, column]})
    return {'status': 'candidate', 'certificate': {**base, 'kind': 'closed_observation', 'states': nodes}}
