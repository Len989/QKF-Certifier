"""Small, total composition language for branches and calls to checked regions.

This JSON AST IS the externally supplied wrapper program. It is not an inferred
Java wrapper or the full Graal helper. Only two named region roles can be called,
once each; no loops, arbitrary code, imports, paths, side effects or arithmetic.
Argument identities and call preconditions are checked later, not assumed here.
"""
from copy import deepcopy
import re

from .model import integer, require

SCHEMA = 'qkf-region-composition-program-v1'
INPUTS = ('bound', 'must', 'may')
COMPARE = {'eq', 'ne', 'ult', 'ule', 'ugt', 'uge'}
MAX_NODES, MAX_DEPTH = 64, 16


def program():
    """A fresh example, not the checker definition of acceptable control flow."""
    return {'schema': SCHEMA, 'entry': {
        'op': 'if', 'test': ['ult', 'bound', 'must'],
        'yes': {'op': 'value', 'word': 'must'},
        'no': {'op': 'if', 'test': ['ugt', 'bound', 'may'],
               'yes': {'op': 'empty'},
               'no': {'op': 'call', 'role': 'descending', 'bind': 'floor',
                      'args': {'bound': 'bound', 'must': 'must', 'may': 'may', 'seed': 'must'},
                      'then': {'op': 'if', 'test': ['eq', 'floor', 'bound'],
                               'yes': {'op': 'value', 'word': 'floor'},
                               'no': {'op': 'call', 'role': 'ascending', 'bind': 'next',
                                      'args': {'must': 'must', 'may': 'may', 'seed': 'floor'},
                                      'then': {'op': 'value', 'word': 'next'}}}}}}}


def inspect(program):
    require(type(program) is dict and set(program) == {'schema', 'entry'}
            and program['schema'] == SCHEMA, 'composition program schema')
    nodes, calls, outputs = [], {}, []

    def visit(node, available, depth, path):
        require(depth <= MAX_DEPTH and len(nodes) < MAX_NODES, 'composition syntax budget')
        require(type(node) is dict and type(node.get('op')) is str, 'composition node')
        nodes.append(path)
        op = node['op']
        if op == 'empty':
            require(set(node) == {'op'}, 'empty has no numeric payload')
        elif op == 'value':
            require(set(node) == {'op', 'word'} and type(node['word']) is str
                    and node['word'] in available, 'return a live word')
        elif op == 'if':
            require(set(node) == {'op', 'test', 'yes', 'no'}, 'composition branch fields')
            test = node['test']
            require(type(test) is list and len(test) == 3 and all(type(x) is str for x in test)
                    and test[0] in COMPARE and all(x in available for x in test[1:]),
                    'branch compares live unsigned words')
            visit(node['yes'], available, depth + 1, path + '.yes')
            visit(node['no'], available, depth + 1, path + '.no')
        elif op == 'call':
            require(set(node) == {'op', 'role', 'bind', 'args', 'then'}, 'composition call fields')
            role, name, args = node['role'], node['bind'], node['args']
            require(type(role) is str and role in {'ascending', 'descending'} and role not in calls,
                    'at most one static call of each fixed region role')
            require(type(name) is str and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,31}', name)
                    and name not in set(INPUTS) | {'alternative'} | set(outputs), 'fresh call result')
            required = {'must', 'may', 'seed'} | ({'bound'} if role == 'descending' else set())
            require(type(args) is dict and set(args) == required
                    and all(type(x) is str and x in available for x in args.values()), 'live call arguments')
            calls[role] = {'bind': name, 'args': dict(args), 'path': path}
            outputs.append(name)
            visit(node['then'], available | {name}, depth + 1, path + '.then')
        else:
            raise ValueError('unsupported composition operation: ' + op)

    visit(program['entry'], set(INPUTS), 0, 'entry')
    return {'names': [*INPUTS, *outputs, 'alternative'], 'calls': calls, 'nodes': len(nodes)}


def compare(test, values):
    op, left, right = test
    a, b = values[left], values[right]
    return {'eq': a == b, 'ne': a != b, 'ult': a < b,
            'ule': a <= b, 'ugt': a > b, 'uge': a >= b}[op]


def execute(program, inputs, invoke):
    """Interpret the actual wrapper. invoke executes supplied source operations.

Call preconditions belong to the source profile and are validated by invoke;
they are not converted into successful returns. The complete trace is data.
"""
    inspect(program)
    values = {k: inputs[k] for k in INPUTS}
    trace = []
    node, path = program['entry'], 'entry'
    while True:
        op = node['op']
        if op == 'if':
            chosen = 'yes' if compare(node['test'], values) else 'no'
            trace.append({'path': path, 'op': 'if', 'branch': chosen})
            node, path = node[chosen], path + '.' + chosen
        elif op == 'call':
            arguments = {k: values[v] for k, v in node['args'].items()}
            output = invoke(node['role'], inputs['width'], arguments)
            require(integer(output, 0, (1 << inputs['width']) - 1), 'region returns a payload word')
            values[node['bind']] = output
            trace.append({'path': path, 'op': 'call', 'role': node['role'],
                          'arguments': arguments, 'bind': node['bind'], 'output': output})
            node, path = node['then'], path + '.then'
        else:
            result = {'kind': 'empty'} if op == 'empty' else {'kind': 'value', 'value': values[node['word']]}
            trace.append({'path': path, 'op': op, 'result': result})
            return {'result': result, 'trace': trace}


def variants():
    """Control-flow/argument controls derived from the executable JSON example."""
    base = program()
    result = {'original': base}
    p = deepcopy(base)
    p['entry']['test'][0] = 'ule'  # equality at minimum takes the early return
    result['inclusive_minimum'] = p
    p = deepcopy(base)
    p['entry']['no']['test'][0] = 'uge'
    result['empty_at_maximum'] = p
    p = deepcopy(base)
    p['entry']['no']['test'] = ['ult', 'bound', 'bound']
    result['missing_empty_guard'] = p
    p = deepcopy(base)
    p['entry']['no']['no']['then']['yes'] = {'op': 'empty'}
    result['empty_on_exact_hit'] = p
    p = deepcopy(base)
    p['entry']['no']['no']['then']['test'][0] = 'ule'
    result['return_floor_in_gap'] = p
    p = deepcopy(base)
    p['entry']['no']['no']['then']['test'] = ['ult', 'floor', 'floor']
    result['always_successor'] = p
    p = deepcopy(base)
    p['entry']['no']['no']['then']['no']['args']['seed'] = 'must'
    result['wrong_successor_seed'] = p
    p = deepcopy(base)
    p['entry']['no']['no']['then']['no']['args']['may'] = 'must'
    result['changed_successor_mask'] = p
    p = deepcopy(base)
    p['entry']['no']['no']['then']['no']['then']['word'] = 'may'
    result['return_maximum_after_successor'] = p
    return result
