"""Registered development tasks, deliveries and independent follow-up requests."""
from copy import deepcopy
from research.causal_comparison.fixtures import cases as previous_cases

SINGLE = ['sdk_default', 'sdk_reuse', 'sdk_direct', 'sdk_ordinary', 'direct41']
SERIES = ['sdk_default', 'sdk_reuse', 'sdk_direct', 'once_default', 'once_ordinary',
          'each_default', 'each_ordinary']


def cases():
    originals = list(previous_cases())
    for old in originals:
        case = deepcopy(old)
        case['previous_case_name'] = old['name']
        case['followups'] = []
        case['unavailable'] = {}
        if old['group'] == 'source_comparison':
            case.update(routes=SINGLE[:], shard='core')
            case['expected'] = {r: old['expected']['sdk_default'] for r in SINGLE}
        elif old['group'] == 'diagnostic':
            case.update(routes=['sdk_default', 'sdk_ordinary', 'direct41'], shard='core')
            case['expected'] = {r: old['expected']['sdk_default'] for r in case['routes']}
            case['expected']['direct41'] = old['expected']['direct41']
        elif old['group'] == 'cold_series':
            case.update(routes=SERIES[:], shard=old['family'] if old['family'] in ('mask', 'parity') else 'repeat')
            case['expected'] = {r: 'certified' for r in SERIES}
        else:
            case['shard'] = 'phase'
        yield case
    anchor = deepcopy(next(c for c in originals if c['name'] == 'batch_mask_all_1'))
    anchor.update(name='assess_boundaries', group='assessment', shard='assessment',
                  previous_case_name='batch_mask_all_1', routes=['once_default', 'once_ordinary'],
                  expected={'once_default': 'certified', 'once_ordinary': 'certified'}, unavailable={})
    q = anchor['request']['query']['requests'][0]
    followups = []
    def add(name, request, status, reason):
        followups.append(dict(name=name, request=request, status=status, reason=reason))
    same = deepcopy(anchor['request'])
    same['query']['requests'][0]['target']['goal'] = ['not', ['nonnegative']]
    add('equivalent_consumer', same, 'certified', 'exact_target_class_agreement')
    wrong = deepcopy(anchor['request'])
    wrong['query']['requests'][0]['target']['goal'] = ['nonnegative']
    add('wrong_consumer', wrong, 'unresolved', 'consumer_not_established_by_summary')
    for name, key, value in [('changed_guard', 'guards', []),
                             ('changed_width', 'width', dict(kind='fixed', bits=8))]:
        different = deepcopy(anchor['request'])
        different['query']['requests'][0][key] = value
        add(name, different, 'unresolved', 'different_selection_guard_or_width')
    different = deepcopy(anchor['request'])
    different['query']['requests'][0]['target']['source']['entry']['method'] = 'other'
    add('changed_selection', different, 'unresolved', 'different_selection_guard_or_width')
    phase = deepcopy(next(c for c in originals if c['name'] == 'phase_pilot_1')['request'])
    add('changed_profile', phase, 'unresolved', 'different_semantic_profile')
    anchor['followups'] = followups
    yield anchor
