"""Exact sources, independent requests and controls, fixed before measurement."""
from research.source_query.context import make_request
from research.source_query.fixtures import cases as query_cases, target
from research.source_planner.fixtures import cases as planner_cases
from research.source_lemmas.fixtures import cases as lemma_cases
from research.source_forcing.fixtures import cases as phase_cases
from research.applicable_summary.contract import SIGNED, PHASE, REQUEST

BASE = 'b7e500bf5636b59b2f04f309d7fbddc83cd40186'
SDK = ('sdk_default', 'sdk_reuse', 'sdk_direct')
SINGLE = ('retained', 'direct41', 'query41', 'planner43', 'eager43') + SDK
PHASE_ROUTES = ('phase_forcing', 'phase_no_saturation', 'phase_direct_seeds', 'phase_direct_cell')


def applications(request, status):
    if status != 'certified':
        return []
    if request['profile'] == PHASE:
        return [dict(input=x, output=y) for x, y in request['query']['goals']]
    from research.signed_predicates.frontend import target_value
    q = request['query']['requests'][0]
    widths = [8, 32] if q['width']['kind'] == 'all_positive' else [q['width']['bits']]
    out = []
    for width in widths:
        for x in (0, 1, 1 << (width - 1), (1 << width) - 1):
            count, sign = x.bit_count(), x >> (width - 1)
            if all(target_value(g, count, sign) for g in q['guards']):
                out.append(dict(input=x, width=width, output=target_value(q['target']['goal'], count, sign)))
    return out


def single(row, group, routes):
    req = dict(schema=REQUEST, profile=SIGNED,
               query=dict(schema='qkf-source-lemma-batch-v1', requests=[row['request']]))
    expected = row['expected']
    if type(expected) is dict:
        expected = expected['planner']
    limits = {**dict(max_work=20_000_000, max_fact_attempts=2048,
                    max_witness_width=8, max_witness_evaluations=510,
                    max_source_states=64, max_product_states=8192), **row['limits']}
    outcomes = {r: expected for r in routes}
    if expected == 'budget_exhausted':
        outcomes.update({r: 'unresolved' for r in routes if r in SDK})
    unavailable = {}
    q = row['request']
    if 'retained' in routes:
        if q['guards'] or q['width']['kind'] != 'all_positive':
            unavailable['retained'] = 'PR38/39 has no conditional/fixed-width consumer contract'
        elif expected == 'budget_exhausted':
            unavailable['retained'] = 'native-question budget has no counterpart in PR38/39'
        elif row['name'] == 'power_unconditional':
            outcomes['retained'] = 'certified'
    return dict(name=row['name'], family=row['family'], group=group, source=row['source'],
                request=req, limits=limits, routes=list(routes), expected=outcomes,
                unavailable=unavailable, applications=applications(req, expected))


def cases():
    rows = {r['name']: r for r in planner_cases()}
    for name in ('mask_31', 'mask_short_circuit', 'arithmetic_compound', 'parity_short_circuit'):
        yield single(rows[name], 'source_comparison', SINGLE)
    originals = {r['name']: r for r in query_cases()}
    for name in ('mask_mutant', 'arithmetic_guarded_mutant', 'mask_fixed_alias',
                 'mask_alias_all_widths', 'empty_guard', 'power_open',
                 'unsupported_dead_statement', 'fact_budget'):
        yield single(originals[name], 'diagnostic', ('retained', 'direct41', 'sdk_default'))
    power = dict(name='power_unconditional', family='representation_gap',
        source='class Demo { static boolean f(long x) { return (x&(x-1))==0; } }',
        request=make_request(target(['popcount_le', 1])), limits={}, expected='unresolved')
    yield single(power, 'diagnostic', ('retained', 'direct41', 'sdk_default'))
    for row in lemma_cases():
        if row['family'] not in ('mask', 'parity', 'ordinary_cache'):
            continue
        req = dict(schema=REQUEST, profile=SIGNED, query=row['request'])
        yield dict(name='batch_' + row['name'], family=row['family'], group='cold_series',
                   source=row['source'], request=req, limits=row['limits'], routes=list(SDK),
                   expected={r: 'certified' for r in SDK}, unavailable={},
                   applications=applications(req, 'certified'))
    for row in phase_cases():
        if row['name'] not in ('pilot_1', 'pilot_4', 'pilot_16', 'wrong_value', 'mandatory_gap', 'forcing_budget'):
            continue
        req = dict(schema=REQUEST, profile=PHASE, query=row['request'])
        expected = {'phase_' + r: ('unresolved' if v == 'budget_exhausted' else v)
                    for r, v in row['expected'].items()}
        # Forcing/no-saturation may leave this goal open. Apply only on routes
        # that independently certify it, with the originally requested output.
        yield dict(name='phase_' + row['name'], family='physical_phases', group='phase',
                   source=row['source'], request=req, limits=row['limits'], routes=list(PHASE_ROUTES),
                   expected=expected, unavailable={}, applications=applications(req, 'certified'))
