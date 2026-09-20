"""Exact development population fixed before the recorded PR41 comparison."""
from .context import make_request

TRUE = ['or', ['negative'], ['nonnegative']]
FALSE = ['and', ['negative'], ['nonnegative']]


def target(formula, word_type='long', cls='Demo', method='f'):
    return {'schema': 'qkf-target-v2', 'kind': 'signed_boolean_predicate',
            'source': {'entry': {'class': cls, 'method': method}, 'word_type': word_type},
            'goal': formula}


def cases():
    # name, family, expression, goal, guards, width, fallback, expected status
    rows = [
        ('mask_31', 'equality_mask', 'x != 2147483648L || (x & 1) == 0', TRUE, [], None, False, 'certified'),
        ('mask_61', 'equality_mask', 'x != 2305843009213693952L || (x & 7) == 0', TRUE, [], None, False, 'certified'),
        ('mask_bits', 'equality_mask', 'x != 42 || (x & 10) == 10', TRUE, [], None, False, 'certified'),
        ('mask_compound', 'equality_mask', '(x != 32 || (x & 3) == 0) && x < 0', ['negative'], [], None, False, 'certified'),
        ('mask_two', 'equality_mask', '(x != 32 || (x & 7) == 0) && (x != 33 || (x & 1) == 1)', TRUE, [], None, False, 'certified'),
        ('mask_mutant', 'equality_mask', 'x != 3 || (x & 1) == 0', TRUE, [], None, False, 'refuted'),
        ('mask_fixed_alias', 'equality_mask', 'x != 2 || (x & 1) == 2', TRUE, [], 1, False, 'certified'),
        ('mask_alias_all_widths', 'equality_mask', 'x != 2 || (x & 1) == 2', TRUE, [], None, False, 'refuted'),
        ('mask_guard_zero', 'equality_mask', '(x & 7) == 0', TRUE, [['popcount_eq', 0]], None, False, 'certified'),
        ('mask_guard_zero_changed', 'equality_mask', '(x & 7) == 0', TRUE, [['positive']], None, False, 'refuted'),
        ('double_even', 'arithmetic_low_bits', '((x+x) & 1) == 0', TRUE, [], None, False, 'certified'),
        ('double_odd', 'arithmetic_low_bits', '((x+x+1) & 1) == 1', TRUE, [], None, False, 'certified'),
        ('subtract_even', 'arithmetic_low_bits', '(((x+3)-(x+1)) & 1) == 0', TRUE, [], None, False, 'certified'),
        ('xor_even', 'arithmetic_low_bits', '((x^x) & 1) == 0', TRUE, [], None, False, 'certified'),
        ('arithmetic_compound', 'arithmetic_low_bits', '(((x+x) & 1) == 0) && x >= 0', ['nonnegative'], [], None, False, 'certified'),
        ('arithmetic_guarded_mutant', 'arithmetic_low_bits', '((x+1) & 1) == 0', TRUE, [['positive']], None, False, 'refuted'),
        ('signed_guard', 'guards', 'x < 0', FALSE, [['nonnegative']], None, False, 'certified'),
        ('signed_changed_guard', 'guards', 'x < 0', FALSE, [['negative']], None, False, 'refuted'),
        ('zero_bridge', 'guards', 'x == 0', ['popcount_eq', 0], [], None, False, 'certified'),
        ('empty_guard', 'guards', 'x == 4611686018427387904L', ['positive'], [['negative'], ['nonnegative']], None, False, 'verified_empty_domain'),
        ('empty_fixed_guard', 'guards', 'x != 0', TRUE, [['popcount_eq', 2]], 1, False, 'verified_empty_domain'),
        ('not_empty_other_width', 'guards', 'x != 0', TRUE, [['popcount_eq', 2]], 2, False, 'certified'),
        ('power_open', 'control', '(x & (x-1)) == 0', ['popcount_eq', 1], [['positive']], None, False, 'unresolved'),
        ('power_guarded_fallback', 'control', '(x & (x-1)) == 0', ['popcount_eq', 1], [['positive']], None, True, 'certified'),
        ('power_wrong_guard', 'control', '(x & (x-1)) == 0', ['popcount_eq', 1], [['nonnegative']], None, True, 'refuted'),
        ('fixed_fallback', 'control', '(x & (x-1)) == 0', ['popcount_eq', 1], [['positive']], 4, True, 'certified'),
        ('late_open', 'control', 'x == 256 && x > 0', FALSE, [], None, False, 'unresolved'),
        ('unsupported_shift', 'unsupported', '(x << 1) == 0', TRUE, [], None, False, 'unsupported'),
    ]
    for name, family, expr, expected, guards, width, fallback, status in rows:
        source = 'class Demo { public static boolean f(long x) { return ' + expr + '; } }'
        yield {'name': name, 'family': family, 'source': source,
               'request': make_request(target(expected), guards, width),
               'fallback': fallback, 'limits': {}, 'expected': status}
    yield {'name': 'renamed_nested', 'family': 'equality_mask',
           'source': 'class Renamed { static boolean accepts(final long value) { final long mask = 7; boolean premise = value == 32; long masked = value & mask; return (!premise || masked == 0) && !(value >= 0); } }',
           'request': make_request(target(['negative'], cls='Renamed', method='accepts')),
           'fallback': False, 'limits': {}, 'expected': 'certified'}
    yield {'name': 'arithmetic_locals_int', 'family': 'arithmetic_low_bits',
           'source': 'class Demo { static boolean f(int x) { int twice = x+x; int v = twice+1; return (v & 1) == 1; } }',
           'request': make_request(target(TRUE, word_type='int')),
           'fallback': False, 'limits': {}, 'expected': 'certified'}
    yield {'name': 'unsupported_dead_statement', 'family': 'unsupported',
           'source': 'class Demo { static boolean f(long x) { long ignored = x << 1; return true; } }',
           'request': make_request(target(TRUE), [['negative'], ['nonnegative']]),
           'fallback': False, 'limits': {}, 'expected': 'unsupported'}
    yield {'name': 'fact_budget', 'family': 'budget',
           'source': 'class Demo { static boolean f(long x) { return ((x+x)&1)==0; } }',
           'request': make_request(target(TRUE)),
           'fallback': False, 'limits': {'max_fact_attempts': 0}, 'expected': 'budget_exhausted'}
