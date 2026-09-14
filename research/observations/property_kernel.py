"""Check a closed joint observation against an independently supplied target.

The source factor's cells have already been justified by its forced rows.
This checker only replays a supplied finite closure or one concrete witness;
it does not search for invariants, invoke SMT or execute native Java.
"""
import hashlib

from .model import digest, integer, require
from .source_factor import Runner
from .upper_spec import check_spec, columns, concrete_violation, decode, step, violation
from .word_execution import integer_execute

SCHEMA = 'qkf-masked-upper-property-v1'
MAX_STATES = 8192
MAX_WITNESS = 256


class System:
    def __init__(self, source, source_certificate, spec):
        self.claim = check_spec(spec)
        self.runner = Runner(source, source_certificate).runner
        self.ir = source_certificate['word']['source_ir']
        self.alphabet = columns()
        self.projected = {}
        for c in self.alphabet:
            b, must, may, a, y, z = map(int, c)
            raw = (b, must, may, a)
            right = raw[int(self.ir['comparison_word'][-1]) - 1]
            symbol = f'{a}{may & (1 - must)}{right}{y}'
            require(symbol in self.runner.alphabet, 'complete source/target input projection')
            self.projected[c] = symbol
        self.initial = (self.runner.initial, 0, 0, 0, 0)
        bit = self.runner.queries.index(self.runner.boundary)
        self.accepting = [t[bit] == '1' for t in self.runner.terminal]
        self.binding = {'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                        'source_certificate_sha256': digest(source_certificate),
                        'specification_sha256': digest(spec), 'target_rules': 'unsigned-high-bit-order-v1'}

    def advance(self, state, column):
        return (self.runner.cells[state[0], self.projected[column]], *step(state[1:], column))

    def bad(self, state):
        return violation(self.claim, state[1:]) if self.accepting[state[0]] else None

    def state_valid(self, state):
        return type(state) is list and len(state) == 5 and integer(state[0], 0, len(self.accepting) - 1) \
            and all(type(x) is int and -1 <= x <= 1 for x in state[1:])


def _scope(spec):
    return {'claim': 'masked_upper_' + spec['claim'], 'specification_sha256': digest(spec),
            'preconditions': spec['preconditions'], 'all_positive_payload_widths': True,
            'semantics': 'restricted unsigned mathematical source model',
            'source_connection': 'trusted restricted frontend and word-split rules',
            'native_java_all_widths': False, 'new_lean_theorem': False}


def check(source, source_certificate, spec, certificate):
    system = System(source, source_certificate, spec)
    require(type(certificate) is dict and certificate.get('schema') == SCHEMA
            and certificate.get('kind') in {'closed_observation', 'counterexample'}, 'property certificate kind')
    require(digest(certificate.get('binding')) == digest(system.binding), 'source, model and target binding')
    if certificate['kind'] == 'counterexample':
        require(set(certificate) == {'schema', 'kind', 'binding', 'word', 'values', 'reason'}, 'counterexample fields')
        word = certificate['word']
        require(type(word) is list and 0 < len(word) <= MAX_WITNESS and all(type(c) is str
                and c in system.projected for c in word), 'counterexample column words')
        state = system.initial
        for c in word: state = system.advance(state, c)
        reason = system.bad(state)
        values = decode(word)
        require(reason is not None and reason == certificate['reason'], 'counterexample terminal violation')
        require(digest(certificate['values']) == digest(values), 'counterexample concrete decoding')
        require(concrete_violation(spec, values) == reason, 'independent integer target violation')
        key = (values['width'], values['bound'], values['must'], values['may'], values['seed'])
        require(integer_execute(system.ir, key) == values['output'], 'direct integer source execution')
        scope = _scope(spec); scope['all_positive_payload_widths'] = False
        return {'status': 'refuted', **scope, 'reason': reason, 'counterexample': values,
                'witness_width': len(word), 'checked_by': ['source factor', 'integer execution', 'integer target']}
    require(set(certificate) == {'schema', 'kind', 'binding', 'states'}, 'closed observation fields')
    nodes = certificate['states']
    require(type(nodes) is list and 0 < len(nodes) <= MAX_STATES, 'property state budget')
    states = []; seen = set()
    for i, node in enumerate(nodes):
        require(type(node) is dict and set(node) == {'state', 'parent'} and system.state_valid(node['state']),
                'joint observation fields and carrier')
        state = tuple(node['state']); require(state not in seen, 'distinct joint observations')
        seen.add(state); parent = node['parent']
        if i == 0:
            require(parent is None and state == system.initial, 'property initial observation')
        else:
            require(type(parent) is list and len(parent) == 2 and integer(parent[0], 0, i - 1)
                    and type(parent[1]) is str and parent[1] in system.projected, 'property derivation parent')
            require(system.advance(states[parent[0]], parent[1]) == state, 'property reachability equation')
        require(system.bad(state) is None, 'a protected target obligation fails')
        states.append(state)
    for state in states:
        for column in system.alphabet:
            require(system.advance(state, column) in seen, 'joint observation must be closed under every input column')
    return {'status': 'certified', **_scope(spec), 'closed_states': len(states),
            'checked_transitions': len(states) * len(system.alphabet), 'alphabet_columns': len(system.alphabet),
            'source_factor_classes': len(system.accepting),
            'obligations': spec['obligations'], 'native_validation': 'separate bounded experiment'}
