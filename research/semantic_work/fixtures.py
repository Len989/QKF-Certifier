"""Predeclared development families. All goals are explicit, including intentional mutants."""
from .contract import make_request


def target(goal, word_type='long', method='f'):
    return {'schema': 'qkf-target-v2', 'kind': 'signed_boolean_predicate',
            'source': {'entry': {'class': 'Demo', 'method': method}, 'word_type': word_type}, 'goal': goal}


def cases():
    power = ['and', ['positive'], ['popcount_eq', 1]]
    definitions = [
        ('constant_true', 'true', ['or', ['negative'], ['nonnegative']]),
        ('constant_false', 'false', ['and', ['negative'], ['nonnegative']]),
        ('power_long', 'x > 0 && (x & (x-1)) == 0', power),
        ('power_missing_zero', '(x & (x-1)) == 0', power),
        ('power_missing_sign', 'x != 0 && (x & (x-1)) == 0', power),
        ('negative', 'x < 0', ['negative']),
        ('nonzero', 'x != 0', ['not', ['popcount_eq', 0]]),
        ('tautology_31', 'x == 2147483648L || x != 2147483648L', ['or', ['negative'], ['nonnegative']]),
        ('delayed_31', 'x == 2147483648L', ['and', ['negative'], ['nonnegative']]),
        ('delayed_61', 'x == 2305843009213693952L', ['and', ['negative'], ['nonnegative']]),
        ('delayed_62_budget', 'x == 4611686018427387904L', ['and', ['negative'], ['nonnegative']]),
        ('mask_implication_31', 'x != 2147483648L || (x & 1) == 0', ['or', ['negative'], ['nonnegative']]),
        ('mask_implication_mutant', 'x != 2147483649L || (x & 1) == 0', ['or', ['negative'], ['nonnegative']]),
        ('guarded_false_40', '(x == 1099511627776L) && ((x & 1) == 1)', ['and', ['negative'], ['nonnegative']]),
        ('late_witness', 'x == 256 && x > 0', ['and', ['negative'], ['nonnegative']]),
        ('small_width_only', 'x > 0 || (x == 2 && x < 0)', ['positive']),
        ('unsupported_shift', '(x << 1) == 0', ['and', ['negative'], ['nonnegative']]),
    ]
    for name, expr, goal in definitions:
        source = 'class Demo { public static boolean f(long x) { return ' + expr + '; } }'
        yield name, make_request(source, target(goal))
    name, r = next(iter(cases_simple()))
    yield name, r


def cases_simple():
    source = 'class Demo { public static boolean f(long x) { return x < 0; } }'
    yield 'unsupported_condition', make_request(source, target(['and', ['negative'], ['nonnegative']]), conditions=[['positive']])
