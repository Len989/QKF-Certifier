"""Small source-bound checker for chronological ground equational proof DAGs.

No congruence-closure search is called by replay. Native word semantics is a
separate bridge; the checker proves exactly the supplied finite presentation.
"""
import hashlib
import json


def tree(value): return tuple(map(tree, value)) if isinstance(value, (list, tuple)) else value
def digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
def depth(term): return 0 if isinstance(term, str) else 1 + max(map(depth, term[1:]))


def validate_term(term, source):
    if isinstance(term, str):
        if term not in source['constants']: raise ValueError('constant')
    elif isinstance(term, tuple) and term and term[0] in source['signature'] and len(term) == 1+source['signature'][term[0]]:
        for child in term[1:]: validate_term(child, source)
    else:
        raise ValueError('term syntax')


def verify(source, certificate, max_nodes=10000):
    if source.get('schema') != 'qkf-ground-obligation-v1': raise ValueError('source schema')
    if certificate.get('schema') != 'qkf-ground-dag-v1' or certificate.get('source_hash') != digest(source):
        raise ValueError('certificate binding')
    equations = [tuple(map(tree, pair)) for pair in source['equations']]
    query = tuple(map(tree, source['query']))
    for pair in equations+[query]:
        if len(pair) != 2: raise ValueError('equation')
        for term in pair: validate_term(term, source)
    nodes = certificate.get('nodes')
    if not isinstance(nodes, list) or not 0 < len(nodes) <= max_nodes: raise ValueError('proof nodes')
    derived = []
    maximum = 0
    for node in nodes:
        def premise(index):
            if type(index) is not int or not 0 <= index < len(derived): raise ValueError('nonchronological premise')
            return derived[index]
        kind = node.get('kind')
        if kind == 'input':
            index = node['equation']
            if type(index) is not int or not 0 <= index < len(equations): raise ValueError('input index')
            result = equations[index]
        elif kind == 'refl':
            term = tree(node['term']); validate_term(term, source); result = (term, term)
        elif kind == 'sym':
            left, right = premise(node['premise']); result = (right, left)
        elif kind == 'trans':
            a, b = premise(node['left']); c, d = premise(node['right'])
            if b != c: raise ValueError('transitivity middle')
            result = (a, d)
        elif kind == 'congr':
            op = node['operation']; ids = node['premises']
            if op not in source['signature'] or len(ids) != source['signature'][op]: raise ValueError('congruence arity')
            arguments = [premise(index) for index in ids]
            result = ((op, *(pair[0] for pair in arguments)), (op, *(pair[1] for pair in arguments)))
        else:
            raise ValueError('proof rule')
        maximum = max(maximum, *(depth(term) for term in result)); derived.append(result)
    root = certificate.get('root')
    if type(root) is not int or not 0 <= root < len(derived) or derived[root] != query:
        raise ValueError('query not proved')
    return dict(status='proved_from_ground_presentation', proof_nodes=len(nodes), maximum_term_depth=maximum)


def verify_model(source, model, horizon):
    """Check ALL active input equations and separation at the stated horizon."""
    size = model['size']
    if type(size) is not int or size < 1: raise ValueError('model size')
    if type(horizon) is not int or horizon < max(depth(tree(t)) for t in source['query']): raise ValueError('model horizon')
    values = model['constants']; tables = model['operations']
    if set(values) != set(source['constants']): raise ValueError('model constants')
    if any(type(v) is not int or not 0 <= v < size for v in values.values()): raise ValueError('constant value')
    if type(model['default']) is not int or not 0 <= model['default'] < size: raise ValueError('default value')
    if set(tables) != set(source['signature']): raise ValueError('model operations')
    for operation, table in tables.items():
        for key, value in table.items():
            args = key.split(',')
            if len(args) != source['signature'][operation] or any(not a.isdigit() or not 0 <= int(a) < size for a in args): raise ValueError('operation tuple')
            if type(value) is not int or not 0 <= value < size: raise ValueError('operation value')
    def evaluate(term):
        if isinstance(term, str): return values[term]
        args = [evaluate(t) for t in term[1:]]
        key = ','.join(map(str, args))
        value = tables[term[0]].get(key, model['default'])
        if type(value) is not int or not 0 <= value < size: raise ValueError('operation value')
        return value
    checked = 0
    for equation in source['equations']:
        if max(depth(tree(t)) for t in equation) <= horizon:
            if evaluate(equation[0]) != evaluate(equation[1]): raise ValueError('active equation violated')
            checked += 1
    if evaluate(source['query'][0]) == evaluate(source['query'][1]): raise ValueError('query not separated')
    return dict(status='separated_at_horizon', horizon=horizon, active_equations_checked=checked, size=size)
