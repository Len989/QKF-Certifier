"""PR44 exact development population; frozen before comparative execution."""
from research.source_query.context import make_request
from research.source_query.fixtures import target, TRUE

BASE = 'f33467297ad3fd4b1767541636ee7fbdf6a844ed'
ROUTES = ('reuse', 'direct_cache', 'no_lemmas')
DEFAULTS = dict(max_work=20_000_000, max_fact_attempts=2048, max_rounds=512,
                max_horizon=128, max_witness_width=8, max_witness_evaluations=510,
                max_source_states=64, max_product_states=8192, max_lemmas=64)
MASK = ('class Demo { static boolean f(long x) { return (x<0) && '
        '((x!=128 || (x&7)==0) && (x!=64 || (x&15)==0)); } }')
PARITY = ('class Demo { static boolean f(long x) { return (x<0) && '
          '((((x+x)&1)==0) && ((((x+x)+2)&1)==0)); } }')


def goals():
    n = ['negative']
    return [n, ['not', ['nonnegative']],
        ['and', n, ['popcount_le', 1]], ['and', n, ['popcount_le', 2]],
        ['and', n, ['popcount_le', 3]], ['and', ['popcount_le', 1], n],
        ['or', n, ['popcount_eq', 2]], ['or', n, ['popcount_eq', 3]],
        ['or', ['popcount_eq', 2], n], ['xor', n, ['popcount_eq', 2]],
        ['xor', ['popcount_eq', 3], n], ['and', n, ['not', ['popcount_eq', 2]]],
        ['and', ['not', ['popcount_eq', 3]], n],
        ['or', n, ['not', ['popcount_le', 1]]],
        ['xor', n, ['not', ['popcount_le', 2]]],
        ['and', ['not', ['nonnegative']], ['popcount_le', 3]]]


def batch(source, selected, *, guards=None, width=None):
    return dict(schema='qkf-source-lemma-batch-v1', requests=[
        make_request(target(g), [['popcount_le', 1]] if guards is None else guards, width)
        for g in selected])


def case(name, family, source, request, status='certified', limits=None):
    whole = status if status in ('unsupported', 'budget_exhausted') else 'completed'
    expected = dict(status=whole, goals=[] if whole != 'completed' else
                    [status] * len(request['requests']))
    return dict(name=name, family=family, source=source, request=request,
                limits={**DEFAULTS, **({} if limits is None else limits)},
                expected={r: expected for r in ROUTES})


def cases():
    for family, source in (('mask', MASK), ('parity', PARITY)):
        for width, label in ((None, 'all'), (8, 'fixed8')):
            for size in (1, 4, 16):
                yield case(f'{family}_{label}_{size}', family, source,
                           batch(source, goals()[:size], width=width))
    yield case('exact_repeats_16', 'ordinary_cache', MASK, batch(MASK, [goals()[0]] * 16))
    simple = 'class Demo { static boolean f(long x) { return x<0; } }'
    yield case('trivial_native_4', 'promotion_declined', simple, batch(simple, goals()[:4]))
    mutant = MASK.replace('(x&7)==0', '(x&7)==1')
    yield case('mask_wrong_source', 'negative', mutant,
               batch(mutant, goals()[:1], width=8), 'refuted')
    mutant = PARITY.replace('((x+x)&1)', '((x+1)&1)')
    yield case('parity_wrong_source', 'negative', mutant, batch(mutant, goals()[:1]), 'refuted')
    power = 'class Demo { static boolean f(long x) { return (x&(x-1))==0; } }'
    yield case('representation_open', 'unresolved', power,
               batch(power, [['popcount_le', 1]], guards=[]), 'unresolved')
    yield case('empty_guard', 'empty', MASK,
               batch(MASK, goals()[:1], guards=[['negative'], ['nonnegative']]), 'verified_empty_domain')
    unsupported = 'class Demo { static boolean f(long x) { long unused=x>>1; return x<0; } }'
    yield case('unsupported_dead_statement', 'unsupported', unsupported,
               batch(unsupported, goals()[:1]), 'unsupported')
    yield case('fact_budget', 'budget', MASK, batch(MASK, goals()[:4]),
               'budget_exhausted', dict(max_fact_attempts=0))
    yield case('inactive_horizon', 'horizon', MASK, batch(MASK, goals()[:1]),
               'unresolved', dict(max_horizon=0))
