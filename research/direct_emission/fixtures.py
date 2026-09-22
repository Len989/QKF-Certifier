"""PR49 development population, registered before comparative measurements."""
from copy import deepcopy
from research.prepared_context.fixtures import cases as previous
from research.sdk_comparison.fixtures import cases as all_cases

MATRIX = [b + '_' + p for b in ('ordinary', 'query') for p in ('no_lemmas', 'reuse')]


def cases():
    for old in previous():
        c = deepcopy(old)
        prefix = 'each_' if c['shard'] == 'each' else ''
        control = prefix + 'ordinary' if prefix else 'sdk_ordinary' if c['shard'] == 'single' else 'once_ordinary'
        routes = [prefix + version + factor for version in ('emitted_', 'prepared_') for factor in MATRIX] + [control]
        c.update(routes=routes, expected={r: 'certified' for r in routes})
        yield c
    c = deepcopy(next(c for c in all_cases() if c['name'] == 'power_open'))
    routes = ['emitted_query_no_lemmas', 'prepared_query_no_lemmas', 'sdk_ordinary']
    c.update(shard='fallback', routes=routes, expected={r: 'unresolved' for r in routes}, pr47_case='power_open')
    yield c
