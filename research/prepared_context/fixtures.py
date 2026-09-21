"""Small PR48 cost slice of fixed PR47 inputs; selected before measurement."""
from copy import deepcopy
from research.sdk_comparison.fixtures import cases as previous_cases

MATRIX = ['prepared_' + b + '_' + p for b in ('ordinary', 'query') for p in ('no_lemmas', 'reuse')]
SELECTED = ('mask_31', 'batch_mask_all_4', 'batch_parity_fixed8_4', 'batch_exact_repeats_16')


def cases():
    originals = {c['name']: c for c in previous_cases()}
    for index, name in enumerate(SELECTED):
        c = deepcopy(originals[name])
        control = 'sdk_ordinary' if index == 0 else 'once_ordinary'
        routes = MATRIX + ['sdk_default', 'sdk_reuse', 'sdk_direct', control]
        c.update(shard=('single', 'mask', 'parity', 'repeat')[index], routes=routes,
                 expected={r: 'certified' for r in routes}, pr47_case=name)
        yield c
    c = deepcopy(originals['batch_mask_all_4'])
    routes = ['each_' + r for r in MATRIX] + ['each_default', 'each_ordinary']
    c.update(name='batch_mask_all_4_each', shard='each', routes=routes,
             expected={r: 'certified' for r in routes}, pr47_case='batch_mask_all_4')
    yield c
