"""Independent masked-upper contracts and exact observations of word order.

Columns are (bound, must, may, seed, output, alternative), low bit first.
The alternative is an independently quantified legal masked word, not a
candidate produced by the source. Prepending a higher bit to two k-bit
numbers preserves their old comparison if those bits agree; otherwise the
higher bit decides, since the old difference is strictly between -2**k
and 2**k. Induction makes the order observation exact at every word length.
"""
import itertools

from .model import digest, require

SCHEMA = 'qkf-masked-upper-spec-v1'
CLAIMS = {'maximum', 'bound'}


def specification(claim='maximum'):
    require(type(claim) is str and claim in CLAIMS, 'unsupported upper claim')
    return {'schema': SCHEMA, 'claim': claim,
            'arguments': {'bound': 1, 'must': 2, 'may': 3, 'seed': 4},
            'optional': 'may & ~must restricted to payload width',
            'preconditions': ['positive payload width', 'extra zero sign bit',
                              'seed & optional == 0', 'seed <= bound'],
            'legal_word': 'seed | s where s is a subset of optional',
            'obligations': ['legal output', 'output <= bound'] +
                           (['every legal alternative <= bound is <= output'] if claim == 'maximum' else []),
            'empty_carrier': 'outside precondition; no output or emptiness verdict is certified',
            'arithmetic': 'unsigned mathematical words; native overflow not covered'}


def check_spec(spec):
    require(type(spec) is dict and type(spec.get('claim')) is str and spec['claim'] in CLAIMS,
            'independently supplied supported specification required')
    require(digest(spec) == digest(specification(spec['claim'])), 'unsupported or changed specification contract')
    return spec['claim']


def columns():
    result = []
    for b, must, may, a in itertools.product((0, 1), repeat=4):
        optional = may & (1 - must)
        if a & optional: continue
        legal = range(a, a + optional + 1)
        for y, z in itertools.product(legal, repeat=2):
            result.append(''.join(map(str, (b, must, may, a, y, z))))
    return sorted(result)


def extend_order(old, left, right):
    return old if left == right else left - right


def step(observation, column):
    b, must, may, a, y, z = map(int, column)
    ab, yb, zb, zy = observation
    return (extend_order(ab, a, b), extend_order(yb, y, b),
            extend_order(zb, z, b), extend_order(zy, z, y))


def violation(claim, observation):
    ab, yb, zb, zy = observation
    if ab > 0: return None
    if yb > 0: return 'above_bound'
    if claim == 'maximum' and zb <= 0 and zy > 0: return 'not_maximal'
    return None


def decode(word):
    values = [sum(int(c[j]) << i for i, c in enumerate(word)) for j in range(6)]
    b, must, may, a, y, z = values
    return {'width': len(word), 'bound': b, 'must': must, 'may': may, 'seed': a,
            'optional': may & ~must, 'output': y, 'alternative': z}


def concrete_violation(spec, values):
    claim = check_spec(spec)
    a, o, b, y, z = (values[k] for k in ['seed', 'optional', 'bound', 'output', 'alternative'])
    def legal(x): return x & a == a and x & ~(a | o) == 0
    require(values['width'] > 0 and a & o == 0 and a <= b, 'counterexample must satisfy input preconditions')
    require(legal(y) and legal(z), 'counterexample masked-word legality')
    if y > b: return 'above_bound'
    if claim == 'maximum' and z <= b and z > y: return 'not_maximal'
    return None
