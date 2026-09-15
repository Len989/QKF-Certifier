"""Independent masked-ceiling target and the two exact reusable lemma contracts.

The target is a tagged value/empty result, not a numeric sentinel. Dependencies
are fixed, externally checked run-2 formulas, not goals chosen by a certificate.
There is no source search, template-module import or Java execution here.
"""
from .model import digest, integer, require

SCHEMA = 'qkf-masked-ceiling-spec-v1'
RULES = 'masked-extrema-floor-successor-weak-orders-v1'
ROLES = ('descending', 'ascending')


def specification():
    return {
        'schema': SCHEMA, 'claim': 'masked_ceiling',
        'semantics': 'unsigned mathematical payload; tagged value or empty',
        'preconditions': ['w is a positive integer', '0 <= bound, must, may < 2^w',
                          'must subset may'],
        'legal_words': '{x in [0, 2^w): (x & must) == must and (x & ~may) == 0}',
        'obligations': ['Value(y) iff a legal word >= bound exists',
                        'Value(y) implies legal y and bound <= y',
                        'for every legal z >= bound, Value(y) implies y <= z',
                        'Empty iff no legal word >= bound exists'],
        'result_encoding': {'value': ['kind', 'value'], 'empty': ['kind']},
    }


def check_spec(spec):
    require(type(spec) is dict and digest(spec) == digest(specification()),
            'independent exact masked-ceiling specification')


def dependency_spec(role):
    """Exact v1 word-observation formulas needed by the composition rule.

The descending carrier becomes the shared mask precisely at seed == must.
The successor has CYCLIC behavior; a non-wrapping call is an extra obligation
of the composed program, not a strengthened assumption in this formula.
"""
    require(type(role) is str and role in ROLES, 'known composition dependency')
    if role == 'descending':
        optional = ['bit_and', 'may', ['bit_not', 'must']]
        pre = [['ule', 'seed', 'bound']]
        obligations = [
            ['subset', 'seed', 'output'],
            ['subset', 'output', ['bit_or', 'seed', optional]],
            ['ule', 'output', 'bound'],
            ['implies', ['ule', 'alternative', 'bound'], ['ule', 'alternative', 'output']],
        ]
        domain = 'disjoint-seed-optional-v1'
    else:
        pre = []
        obligations = [
            ['subset', 'must', 'output'], ['subset', 'output', 'may'],
            ['implies', ['ne', 'seed', 'may'], ['ult', 'seed', 'output']],
            ['implies', ['ult', 'seed', 'alternative'], ['ule', 'output', 'alternative']],
            ['implies', ['eq', 'seed', 'may'], ['eq', 'output', 'must']],
        ]
        domain = 'legal-masked-entry-v1'
    return {'schema': 'qkf-word-observation-spec-v1', 'profile': role,
            'domain': domain, 'quantifier': 'forall_legal_alternative',
            'preconditions': pre, 'obligations': obligations}


def validate_input(values, *, max_width=4096):
    require(type(values) is dict and set(values) == {'width', 'bound', 'must', 'may'},
            'composition input fields')
    require(integer(values['width'], 1, max_width), 'positive composition input width')
    mask = (1 << values['width']) - 1
    require(all(integer(values[k], 0, mask) for k in ('bound', 'must', 'may')),
            'composition input word range')
    require(values['must'] & ~values['may'] == 0, 'compatible composition masks')


def valid_result(result, width):
    if type(result) is not dict:
        return False
    if result.get('kind') == 'empty':
        return set(result) == {'kind'}
    return (set(result) == {'kind', 'value'} and result.get('kind') == 'value'
            and integer(result['value'], 0, (1 << width) - 1))


def concrete_violation(spec, inputs, result, alternative):
    """Numerical witness check, independent of weak-order inference.

A witness alternative is always a legal masked word; for a missed value or
nonminimal answer it must also meet the bound. No successor oracle or search
is called by this checker.
"""
    check_spec(spec)
    validate_input(inputs)
    require(valid_result(result, inputs['width']), 'tagged composition result')
    require(integer(alternative, 0, (1 << inputs['width']) - 1), 'alternative range')
    m, a, b = (inputs[k] for k in ('must', 'may', 'bound'))
    legal = lambda x: x & m == m and not x & ~a
    require(legal(alternative), 'independent legal composition alternative')
    if result['kind'] == 'empty':
        return 'empty_with_feasible_value' if alternative >= b else None
    y = result['value']
    if not legal(y):
        return 'output_outside_mask'
    if y < b:
        return 'below_bound'
    if b <= alternative < y:
        return 'not_minimal'
    return None
