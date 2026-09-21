"""Exact PR43 development cases, registered before comparative execution."""
from research.source_query.fixtures import cases as previous_cases, TRUE, target
from research.source_query.context import make_request

BASE = '01541ee22fd59dfe8be2d0453f942984c833d445'
ROUTES = ('planner', 'ordinary', 'eager')
DEFAULTS = dict(max_work=10_000_000, max_fact_attempts=512, max_rounds=256,
                max_horizon=128, max_witness_width=8, max_witness_evaluations=510,
                max_source_states=64, max_product_states=8192)


def cases():
    for case in previous_cases():
        yield {**case, 'limits': {**DEFAULTS, **case['limits']},
               'expected': {route: case['expected'] for route in ROUTES}}
    shared = 'class Demo { static boolean f(long x) { return ((x+x)&1)==0 || x<0; } }'
    extra = [
        ('goal_true', 'goal_change', shared, TRUE, [['negative']], {}, 'certified'),
        ('goal_negative', 'goal_change', shared, ['negative'], [['negative']], {}, 'certified'),
        ('mask_short_circuit', 'equality_mask',
         'class Demo { static boolean f(long x) { return (x!=32 || (x&7)==0) || (x&(x-1))==0; } }',
         TRUE, [], {}, 'certified'),
        ('parity_short_circuit', 'arithmetic_low_bits',
         'class Demo { static boolean f(long x) { return ((x+x)&1)==0 || (x&(x-1))==0; } }',
         TRUE, [], {}, 'certified'),
        ('irrelevant_local', 'early_stop',
         'class Demo { static boolean f(long x) { long ignored=(x+x)&1; return x<0; } }',
         ['negative'], [], {}, 'certified'),
        ('inactive_horizon', 'horizon',
         'class Demo { static boolean f(long x) { return x<0; } }',
         ['negative'], [], {'max_horizon': 0}, 'unresolved'),
        ('bounded_horizon', 'horizon',
         'class Demo { static boolean f(long x) { return false; } }',
         ['nonpositive'], [], {'max_horizon': 0}, 'unresolved'),
    ]
    for name, family, source, goal, guards, limits, expected in extra:
        yield dict(name=name, family=family, source=source,
                   request=make_request(target(goal), guards), fallback=False,
                   limits={**DEFAULTS, **limits}, expected={r: expected for r in ROUTES})
