"""COMPARISON ONLY: identical PR31 pipeline with checked forward-cell transitions.

Both arms retain the full atomic proof and source-bound load, so this ablates
execution representation, NOT all row proof construction/checking. This format
is deliberately rejected by the production v4 checker. No monkeypatching.
"""
from copy import deepcopy

from research.observations.model import digest, require
from research.signed_runtime.runtime import load
from research.signed_targets.common import Monitor, binding, budgets as ceilings, prepare, result
from research.signed_targets.checker import check_product, check_witness

SCHEMA = 'qkf-run32-direct-control-v1'
ENGINE = 'run32-checked-cells-control-not-production'


class DirectMonitor(Monitor):
    def __init__(self, runner, spec, certificate):
        super().__init__(runner, spec)
        cells=certificate['observations']['cells']
        table={(c['state'],c['symbol']):(c['output'],c['next']) for c in cells}
        require(len(table)==2*runner.machine.classes, 'direct control coverage')
        self.table=tuple(tuple(table[i,a] for a in self.alphabet)
                         for i in range(runner.machine.classes))
        require(all(self.table[i][j]==runner.machine.step(i,a)
                    for i in range(runner.machine.classes) for j,a in enumerate(self.alphabet)),
                'direct control must agree with checked atomic action')

    def step(self, state, symbol):
        require(type(symbol) is str and symbol in self.alphabet, 'binary target column')
        bit=int(symbol); output,following=self.table[state[0]][bit]
        require(output=='_', 'terminal-only source output')
        return following,min(self.limit,state[1]+bit),bit


def _result(compiled, inner):
    return {'schema':'qkf-run32-direct-result-v1','status':inner['status'], 'engine':ENGINE,
            'all_positive_widths':inner.get('all_positive_widths',False),'inner':inner,
            'scope':'comparison-only checked-cell action; full row validation retained'}


def check_inner(source,target,certificate):
    target,certificate=deepcopy(target),deepcopy(certificate)
    compiled,selection=prepare(target)
    require(type(certificate) is dict and set(certificate)=={'schema','binding','observations','obligation'}
            and certificate['schema']==SCHEMA,'direct control certificate fields')
    runner,receipt=load(source,selection,certificate['observations'])
    require(digest(certificate['binding'])==digest(binding(compiled,receipt)),'direct binding')
    monitor=DirectMonitor(runner,compiled['specification'],certificate['observations'])
    p=certificate['obligation']
    require(type(p) is dict and p.get('kind') in {'closure','counterexample'},'direct obligation')
    checked=check_product(monitor,p) if p['kind']=='closure' else check_witness(source,selection,monitor,p)
    return result(compiled,receipt,checked)


def check(source,target,envelope):
    compiled,_=prepare(target)
    require(type(envelope) is dict and set(envelope)=={'schema','engine','proof','result'}
            and envelope['schema']==SCHEMA and envelope['engine']==ENGINE,'direct envelope fields')
    fresh=_result(compiled,check_inner(source,target,envelope['proof']))
    require(digest(fresh)==digest(envelope['result']),'direct saved result')
    return fresh


def prove(source,target,*,budgets=None):
    from research.signed_observations.producer import derive
    from research.signed_targets.producer import discover,ProductLimit
    from research.wordexpr.frontend import Unsupported
    compiled,selection=prepare(target); b=ceilings(budgets)
    try:
        observations,outcome=derive(source,selection,**{k:b[k] for k in
                                    ('max_states','max_observations','max_pullbacks','max_classes')})
    except Unsupported as exc:
        return _result(compiled,{'status':'unsupported','stage':'source_profile','reason':str(exc)}),None
    if observations is None:
        return _result(compiled,outcome),None
    runner,receipt=load(source,selection,observations)
    monitor=DirectMonitor(runner,compiled['specification'],observations)
    try:
        obligation=discover(monitor,b['max_target_states'],b['max_witness_bits'])
    except ProductLimit as exc:
        return _result(compiled,{'status':'budget_exhausted','stage':'target_product','reason':str(exc),
                                 'runtime':receipt}),None
    proof={'schema':SCHEMA,'binding':binding(compiled,receipt),'observations':observations,
           'obligation':obligation}
    # Mirror the inner and outer accepted checks in the production unified v4.
    outcome=_result(compiled,check_inner(source,target,proof))
    envelope={'schema':SCHEMA,'engine':ENGINE,'proof':proof,'result':outcome}
    return check(source,target,envelope),envelope
