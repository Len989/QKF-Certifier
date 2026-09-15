"""Four legacy goals expressed as formulas, plus a new composition of predicates.

Templates only construct external specifications. The generic checker never
imports this module or chooses a target by its name.
"""
from .model import require
from .target_rules import DOMAINS, SPEC_SCHEMA, compile_spec


def template(profile, claim):
    require(type(profile) is str and profile in DOMAINS and type(claim) is str, 'target template')
    preconditions = []
    if profile == 'ascending':
        require(claim in {'cyclic_successor', 'membership', 'changes'}, 'ascending target template')
        obligations = [['subset', 'must', 'output'], ['subset', 'output', 'may']]
        if claim == 'cyclic_successor':
            obligations += [
                ['implies', ['ne', 'seed', 'may'], ['ult', 'seed', 'output']],
                ['implies', ['ult', 'seed', 'alternative'], ['ule', 'output', 'alternative']],
                ['implies', ['eq', 'seed', 'may'], ['eq', 'output', 'must']],
            ]
        elif claim == 'changes':
            preconditions = [['ne', 'must', 'may']]
            obligations.append(['ne', 'output', 'seed'])
    else:
        require(claim in {'maximum', 'bound'}, 'descending target template')
        optional = ['bit_and', 'may', ['bit_not', 'must']]
        preconditions = [['ule', 'seed', 'bound']]
        obligations = [
            ['subset', 'seed', 'output'],
            ['subset', 'output', ['bit_or', 'seed', optional]],
            ['ule', 'output', 'bound'],
        ]
        if claim == 'maximum':
            obligations.append(['implies', ['ule', 'alternative', 'bound'],
                                ['ule', 'alternative', 'output']])
    spec = {'schema': SPEC_SCHEMA, 'profile': profile, 'domain': DOMAINS[profile],
            'quantifier': 'forall_legal_alternative', 'preconditions': preconditions,
            'obligations': obligations}
    compile_spec(spec)
    return spec


def from_legacy(spec):
    """Explicit translation, never silent reinterpretation of a legacy schema."""
    if type(spec) is dict and spec.get('schema') == 'qkf-masked-upper-spec-v1':
        from .upper_spec import check_spec
        return template('descending', check_spec(spec))
    from .successor_spec import check_spec
    return template('ascending', check_spec(spec))
