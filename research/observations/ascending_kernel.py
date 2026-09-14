"""Replay source-derived residual offsets and the common QKF observation proof.

At cut k the mutable word is L + 2^k * ((seed >> k) + offset).
L is already emitted. The local rules preserve L, observe only the current
bit and update a constant offset into the untouched high slice. These rules
are trusted mathematical semantics, not a newly mechanized Java theorem.
"""
from .ascending_source import read_source
from .checker import check as check_observations
from .model import MODEL_SCHEMA, Model, digest, integer, require

SCHEMA = 'qkf-ascending-source-factor-v1'
MAX_OFFSET = 255
MAX_STATES = 64
ALPHABET = ('000', '010', '011', '111')  # must <= seed <= may, per bit


def cell(ir, state, symbol):
    registers, offset = list(state[:-1]), state[-1]
    must, may, seed = map(int, symbol)
    bit, high = (seed + offset) % 2, (seed + offset) // 2

    def guard(g):
        if g[0] == 'literal': return g[1]
        if g[0] == 'register': return registers[g[1]]
        if g[0] == 'not': return not guard(g[1])
        if g[0] == 'and': return guard(g[1]) and guard(g[2])
        if g[0] == 'or': return guard(g[1]) or guard(g[2])
        require(g[0] == 'bit', 'compiled Boolean operation')
        value = {'must': must, 'may': may, 'optional': may & (1 - must), 'value': bit}[g[1]]
        return bool(value) == g[2]

    def run(s):
        nonlocal bit, high
        op = s[0]
        if op == 'block':
            for x in s[1]: run(x)
        elif op == 'if': run(s[2] if guard(s[1]) else s[3])
        elif op == 'register_set': registers[s[1]] = guard(s[2])
        elif op == 'add':
            high += (bit + s[1]) // 2; bit = (bit + s[1]) % 2
        elif op == 'set': bit = 1
        elif op == 'clear': bit = 0
        elif op == 'flip': bit = 1 - bit
        else: raise ValueError('compiled word operation')

    run(ir['body'])
    return str(bit), tuple(registers) + (high,)


def state_name(state):
    return 'registers=' + ''.join(str(int(v)) for v in state[:-1]) + ',offset=' + str(state[-1])


def compiled_model(ir, states):
    rows = []
    for state in states:
        for a in ALPHABET:
            y, next_state = cell(ir, state, a)
            rows.append({'state': state_name(state), 'symbol': a, 'output': y, 'next': state_name(next_state)})
    return Model({'schema': MODEL_SCHEMA, 'states': [state_name(s) for s in states],
                  'initial': state_name(tuple(ir['register_initial']) + (0,)),
                  'alphabet': list(ALPHABET), 'outputs': ['0', '1'],
                  'terminal': {state_name(s): 'unobserved' for s in states},
                  'steps': rows, 'binding': {'source_ir': ir, 'rules_version': SCHEMA}}).data


def check_carrier(source, cert):
    require(type(cert) is dict and set(cert) == {'schema', 'source_ir', 'carrier', 'observations'}
            and cert['schema'] == SCHEMA, 'ascending factor certificate fields')
    ir = read_source(source)
    require(digest(cert['source_ir']) == digest(ir), 'ascending source and slice-rule binding')
    records = cert['carrier']
    require(type(records) is list and 0 < len(records) <= MAX_STATES, 'bounded residual carrier')
    states = []
    for i, record in enumerate(records):
        require(type(record) is dict and set(record) == {'state', 'parent'}, 'residual record fields')
        s, parent = record['state'], record['parent']
        require(type(s) is list and len(s) == len(ir['register_initial']) + 1
                and all(type(x) is bool for x in s[:-1]) and integer(s[-1], 0, MAX_OFFSET),
                'Boolean registers and nonnegative integer residual')
        state = tuple(s); require(state not in states, 'distinct source residual')
        if i == 0:
            require(parent is None and s == ir['register_initial'] + [0], 'source initial residual')
        else:
            require(type(parent) is list and len(parent) == 2 and integer(parent[0], 0, i - 1)
                    and type(parent[1]) is str and parent[1] in ALPHABET, 'earlier residual parent')
            require(cell(ir, states[parent[0]], parent[1])[1] == state, 'residual reachability proof')
        states.append(state)
    known = set(states)
    for state in states:
        for symbol in ALPHABET:
            require(cell(ir, state, symbol)[1] in known, 'residual carrier is not closed')
    return ir, states


def check(source, cert):
    ir, states = check_carrier(source, cert)
    observations = check_observations(compiled_model(ir, states), cert['observations'])
    return {'status': 'certified', 'claim': 'source_region_model_equivalence',
            'residual_states': len(states), 'residual_offsets': sorted({s[-1] for s in states}),
            'observations': observations,
            'scope': {'mathematical_payload_widths': 'all positive', 'profile': ir['profile'],
                      'trusted_frontend_and_slice_rules': True, 'whole_helper': False,
                      'native_java_all_widths': False, 'successor_property': 'not certified by this schema',
                      'new_lean_theorem': False}}


class Runner:
    def __init__(self, source, cert):
        self.result = check(source, cert)
        self.initial = cert['observations']['initial']
        self.cells = {(r['state'], r['symbol']): (r['output'], r['next'])
                      for r in cert['observations']['cells']}

    def run(self, word):
        state = self.initial; output = []
        for a in word:
            require(type(a) is str and a in ALPHABET, 'legal ascending input column')
            y, state = self.cells[state, a]; output.append(y)
        return {'outputs': output, 'class': state}
