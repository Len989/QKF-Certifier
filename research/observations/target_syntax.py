"""Compile a typed word-goal formula to exact low-to-high observations.

This module has no source/program-specific transition table. Word expressions
are coordinatewise; equality/support accumulate Boolean answers, and unsigned
order lets a differing higher bit override the lower comparison. The checker
recompiles the external goal: certificate-supplied programs are not trusted.
"""
from .model import digest, require

SPEC_SCHEMA = 'qkf-word-observation-spec-v1'
RULES = 'coordinatewise-words-and-unsigned-order-v1'
DOMAINS = {'ascending': 'legal-masked-entry-v1',
           'descending': 'disjoint-seed-optional-v1'}
COLUMN_NAMES = {'ascending': ('must', 'may', 'seed', 'alternative'),
                'descending': ('bound', 'must', 'may', 'seed', 'output', 'alternative')}
MAX_NODES, MAX_DEPTH, MAX_ATOMS = 512, 16, 16


def compile_spec(spec):
    """Validate a closed grammar and derive only the questions used by this goal.

Additional preconditions may mention inputs, never output or alternative.
The fixed source domain and the independent universal competitor cannot change.
No minimum observation size or satisfiability of extra assumptions is claimed.
"""
    require(type(spec) is dict and set(spec) == {
        'schema', 'profile', 'domain', 'quantifier', 'preconditions', 'obligations'
    } and spec['schema'] == SPEC_SCHEMA, 'typed word specification fields')
    profile = spec['profile']
    require(type(profile) is str and profile in DOMAINS, 'typed source profile')
    require(spec['domain'] == DOMAINS[profile]
            and spec['quantifier'] == 'forall_legal_alternative', 'fixed domain and universal competitor')
    require(type(spec['preconditions']) is list and len(spec['preconditions']) <= 16
            and type(spec['obligations']) is list and 0 < len(spec['obligations']) <= 16,
            'bounded preconditions and nonempty obligations')
    variables = set(COLUMN_NAMES[profile]) | {'output'}
    atoms, ids = [], {}
    nodes = 0

    def visit(depth):
        nonlocal nodes
        nodes += 1
        require(depth <= MAX_DEPTH and nodes <= MAX_NODES, 'target syntax budget')

    def word(expr, depth, input_only):
        visit(depth)
        if type(expr) is str:
            require(expr in variables | {'zero', 'ones'}, 'declared word variable or word constant')
            require(not input_only or expr not in {'output', 'alternative'},
                    'preconditions cannot assume output or competitor facts')
            return
        require(type(expr) is list and expr and type(expr[0]) is str, 'word expression')
        arity = {'bit_not': 1, 'bit_and': 2, 'bit_or': 2, 'bit_xor': 2}.get(expr[0])
        require(arity is not None and len(expr) == arity + 1, 'coordinatewise word operation')
        for child in expr[1:]:
            word(child, depth + 1, input_only)

    def formula(expr, depth, input_only):
        visit(depth)
        if type(expr) is bool:
            return expr
        require(type(expr) is list and expr and type(expr[0]) is str, 'Boolean formula')
        op = expr[0]
        if op in {'not', 'and', 'or', 'implies'}:
            require((len(expr) == 2 if op == 'not' else len(expr) == 3 if op == 'implies'
                     else 3 <= len(expr) <= 17), 'Boolean connective arity')
            return [op, *(formula(e, depth + 1, input_only) for e in expr[1:])]
        require(op in {'eq', 'ne', 'ult', 'ule', 'ugt', 'uge', 'subset', 'disjoint'}
                and len(expr) == 3, 'typed word predicate')
        left, right = expr[1:]
        word(left, depth + 1, input_only)
        word(right, depth + 1, input_only)
        if op in {'ugt', 'uge'}:
            left, right = right, left
            op = {'ugt': 'ult', 'uge': 'ule'}[op]
        kind = 'order' if op in {'ult', 'ule'} else 'eq' if op == 'ne' else op
        atom = {'kind': kind, 'left': left, 'right': right}
        key = digest(atom)
        if key not in ids:
            require(len(atoms) < MAX_ATOMS, 'target observation budget')
            ids[key] = len(atoms)
            atoms.append(atom)
        index = ids[key]
        if kind == 'order':
            return [op, index]
        query = ['query', index]
        return ['not', query] if op == 'ne' else query

    preconditions = [formula(e, 0, True) for e in spec['preconditions']]
    obligations = [formula(e, 0, False) for e in spec['obligations']]
    return {'rules': RULES, 'profile': profile, 'domain': DOMAINS[profile],
            'quantifier': 'forall_legal_alternative', 'atoms': atoms,
            'preconditions': preconditions, 'obligations': obligations}
