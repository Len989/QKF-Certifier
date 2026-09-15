"""Check formula-derived target observations against either existing source factor.

The two source interfaces stay distinct: ascending emits bits; descending
recognizes a graph of input/output words. All target rules come from the
external typed formula, not a target-name-specific state machine.
"""
import hashlib

from .model import digest, integer, require
from .target_rules import (COLUMN_NAMES, RULES, advance, columns, compile_spec,
                           concrete_violation, initial, valid_state, violation)

SCHEMA = 'qkf-word-observation-property-v1'
MAX_STATES, MAX_WITNESS = 8192, 256


class System:
    def __init__(self, source, source_certificate, spec):
        self.program = compile_spec(spec)
        self.profile = spec['profile']
        self.alphabet = columns(self.profile)
        self.names = COLUMN_NAMES[self.profile]
        self.ir = None
        if self.profile == 'ascending':
            from .ascending_kernel import ALPHABET, Runner
            self.runner = Runner(source, source_certificate)
            self.classes = len(source_certificate['observations']['blocks'])
            self.accepting = [True] * self.classes
            require({c[:3] for c in self.alphabet} == set(ALPHABET), 'complete ascending projection')
        else:
            from .source_factor import Runner
            self.runner = Runner(source, source_certificate).runner
            self.ir = source_certificate['word']['source_ir']
            self.classes = len(self.runner.terminal)
            boundary = self.runner.queries.index(self.runner.boundary)
            self.accepting = [t[boundary] == '1' for t in self.runner.terminal]
            projected = {self.project(dict(zip(self.names, map(int, c)))) for c in self.alphabet}
            require(projected & set(self.runner.alphabet) == set(self.runner.alphabet),
                    'complete descending projection')
        start = initial(self.program)
        # A separate nonempty flag avoids accidentally proving/refuting width 0.
        self.initial = (self.runner.initial, False, *start)
        self.dead = (-1, True, *start)
        self.binding = {'source_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(),
                        'source_certificate_sha256': digest(source_certificate),
                        'specification_sha256': digest(spec), 'target_rules': RULES}

    def project(self, env):
        raw = tuple(env[k] for k in ('bound', 'must', 'may', 'seed'))
        right = raw[int(self.ir['comparison_word'][-1]) - 1]
        return f"{env['seed']}{env['may'] & (1 - env['must'])}{right}{env['output']}"

    def transition(self, state, column):
        env = dict(zip(self.names, map(int, column)))
        if state[0] == -1:
            return self.dead, env
        if self.profile == 'ascending':
            y, following = self.runner.cells[state[0], column[:3]]
            env['output'] = int(y)
        else:
            symbol = self.project(env)
            if symbol not in self.runner.alphabet:
                # A graph-rejected output is not a target precondition. Preserve
                # a single rejecting sink, including every subsequent column.
                return self.dead, env
            following = self.runner.cells[state[0], symbol]
        return (following, True, *advance(self.program, state[2:], env)), env

    def advance(self, state, column):
        return self.transition(state, column)[0]

    def bad(self, state):
        if state[0] == -1 or not state[1] or not self.accepting[state[0]]:
            return None
        return violation(self.program, state[2:])

    def state_valid(self, state):
        return (type(state) is list and len(state) == len(self.initial)
                and integer(state[0], -1, self.classes - 1) and type(state[1]) is bool
                and valid_state(self.program, state[2:])
                and (state[0] != -1 or tuple(state) == self.dead))

    def trace(self, word):
        state = self.initial
        values = {k: 0 for k in set(self.names) | {'output'}}
        for i, column in enumerate(word):
            state, env = self.transition(state, column)
            for k, v in env.items():
                values[k] |= v << i
        return state, {'width': len(word), **values}

    def integer_output(self, source, values):
        if self.profile == 'ascending':
            from .ascending_execution import integer_value
            from .ascending_source import extract_region
            key = tuple(values[k] for k in ('width', 'must', 'may', 'seed'))
            return integer_value(extract_region(source), key)
        from .word_execution import integer_execute
        key = tuple(values[k] for k in ('width', 'bound', 'must', 'may', 'seed'))
        return integer_execute(self.ir, key)


def _scope(spec, universal):
    return {'claim': 'word_observation_formula', 'profile': spec['profile'],
            'specification_sha256': digest(spec), 'domain': spec['domain'],
            'quantifier': spec['quantifier'], 'preconditions': spec['preconditions'],
            'obligations': spec['obligations'], 'all_positive_payload_widths': universal,
            'assumption_satisfiability': 'not certified',
            'semantics': 'restricted unsigned mathematical source profile',
            'trusted_frontend_and_slice_rules': True, 'trusted_target_rules': RULES,
            'whole_helper': False, 'native_java_all_widths': False, 'new_lean_theorem': False}


def check(source, source_certificate, spec, certificate):
    system = System(source, source_certificate, spec)
    require(type(certificate) is dict and certificate.get('schema') == SCHEMA
            and certificate.get('kind') in {'closed_observation', 'counterexample'}, 'typed target certificate kind')
    require(digest(certificate.get('binding')) == digest(system.binding), 'typed target source and goal binding')
    require(digest(certificate.get('program')) == digest(system.program),
            'observation program must be recompiled from the external goal')
    common = {'schema', 'kind', 'binding', 'program'}
    if certificate['kind'] == 'counterexample':
        require(set(certificate) == common | {'word', 'values', 'reason'}, 'typed counterexample fields')
        word = certificate['word']
        require(type(word) is list and 0 < len(word) <= MAX_WITNESS
                and all(type(c) is str and c in system.alphabet for c in word), 'legal independent witness columns')
        state, values = system.trace(word)
        reason = system.bad(state)
        require(reason is not None and certificate['reason'] == reason, 'protected formula violation')
        require(digest(values) == digest(certificate['values']), 'typed witness decoding')
        require(concrete_violation(spec, values) == reason, 'independent whole-integer target violation')
        require(system.integer_output(source, values) == values['output'], 'independent integer source execution')
        return {'status': 'refuted', **_scope(spec, False), 'reason': reason,
                'counterexample': values, 'witness_width': len(word),
                'observations': len(system.program['atoms']),
                'checked_by': ['source factor', 'integer source execution', 'integer target formula']}
    require(set(certificate) == common | {'states'}, 'typed closed-observation fields')
    nodes = certificate['states']
    require(type(nodes) is list and 0 < len(nodes) <= MAX_STATES, 'typed target state budget')
    states, seen = [], set()
    for i, node in enumerate(nodes):
        require(type(node) is dict and set(node) == {'state', 'parent'}
                and system.state_valid(node['state']), 'typed target observation state')
        state, parent = tuple(node['state']), node['parent']
        require(state not in seen, 'distinct typed target states')
        if i == 0:
            require(parent is None and state == system.initial, 'typed target initial observation')
        else:
            require(type(parent) is list and len(parent) == 2 and integer(parent[0], 0, i - 1)
                    and type(parent[1]) is str and parent[1] in system.alphabet, 'typed target parent')
            require(system.advance(states[parent[0]], parent[1]) == state, 'typed target reachability equation')
        require(system.bad(state) is None, 'a protected formula obligation fails')
        states.append(state)
        seen.add(state)
    for state in states:
        for column in system.alphabet:
            require(system.advance(state, column) in seen, 'closure under every independent input/output column')
    return {'status': 'certified', **_scope(spec, True), 'closed_states': len(states),
            'checked_transitions': len(states) * len(system.alphabet),
            'alphabet_columns': len(system.alphabet), 'observations': len(system.program['atoms']),
            'source_factor_classes': system.classes, 'source_rejecting_sink': system.dead in seen,
            'minimality': 'not claimed', 'native_validation': 'separate bounded experiment'}
