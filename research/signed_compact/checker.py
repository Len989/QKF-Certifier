"""Source-bound compact verification, without expanding all pair witnesses.

Transport sharing is exact JSON sharing only. Mathematical obligations still
check source reduction, every coverage edge, observations, labelled atomic rows
and every independently supplied target. No producer is imported here.
"""
from dataclasses import dataclass
from research.observations.model import Model, digest, require, integer, ATOMIC_CERT_SCHEMA
from research.signed_coverage.checker import rebuild
from research.signed_coverage.local import OBS_SCHEMA as OLD_SOURCE_SCHEMA, EMPTY
from research.signed_runtime.core import AtomicRow, Machine
from research.signed_runtime.runtime import Runner
from research.signed_targets.common import prepare, Monitor
from research.signed_targets.checker import check_product
from research.signed_context.witness import check_ir
from research.signed_context.io import freeze, thaw, source_text
from research.unified.checker import InvalidProof
from . import dag, finite

SCHEMA = 'qkf-signed-compact-target-bundle-v1'
SOURCE_SCHEMA = 'qkf-signed-guarded-compact-observations-v1'
ENGINE = 'signed-compact-coverage-v1'
_KEY = object()


def check_source(source, selection, certificate):
    require(type(certificate) is dict and set(certificate) == {'schema', 'source_model', 'observations'}
            and certificate['schema'] == SOURCE_SCHEMA, 'compact source proof envelope')
    original, _, model, metrics = rebuild(source, selection, certificate['source_model'])
    obs = certificate['observations']
    checked = finite.check(model.data, obs)
    blocks = obs['blocks']
    require(blocks[obs['initial']] == [model.initial] and model.terminal[model.initial] == EMPTY,
            'protected empty source observation')
    rows_by_label = {(r['symbol'], r['output']): r for r in obs['rows']}
    rows = tuple(tuple(AtomicRow(tuple(dict(rows_by_label[a, y]['supplied'])[1 << j]
                          for j in range(len(blocks)))) for y in model.outputs) for a in model.alphabet)
    machine = Machine(tuple(model.alphabet), tuple(model.outputs),
                      tuple(model.terminal[b[0]] for b in blocks), obs['initial'], rows)
    cells = [{'symbol': a, 'state': i, 'output': machine.step(i, a)[0], 'next': machine.step(i, a)[1]}
             for a in machine.alphabet for i in range(machine.classes)]
    require(cells == obs['cells'], 'compact atomic extraction agrees with checked cells')
    identity = {'source_sha256': original['source_sha256'], 'request_sha256': digest(selection),
                'certificate_sha256': digest(certificate), 'model_sha256': model.sha256,
                'contract': selection['contract'], 'word_type': selection['word_type']}
    runner = Runner(machine, tuple(sorted(identity.items())))
    receipt = {'schema': 'qkf-signed-compact-source-result-v1', 'status': 'source_runtime_verified',
               'identity': identity, 'action_sha256': digest(machine.snapshot()), 'coverage': metrics,
               'observation': checked, 'target_checked': False, 'lean_checked': False,
               'scope': 'retained modular signed profile; checked source/reduction/coverage and atomic rows'}
    return original, model, runner, receipt


def check_target(ir, selection, runner, receipt, target, obligation):
    compiled, expected_selection = prepare(target)
    require(freeze(selection) == freeze(expected_selection), 'target entry/type/contract differs')
    require(type(obligation) is dict and obligation.get('kind') in {'closure', 'counterexample'},
            'compact target obligation')
    monitor = Monitor(runner, compiled['specification'])
    verified = (check_product(monitor, obligation) if obligation['kind'] == 'closure'
                else check_ir(ir, selection, monitor, obligation))
    return {'schema': 'qkf-signed-compact-target-result-v1', 'engine': ENGINE,
            'status': verified['status'], 'claim': 'source_matches_independent_target_through_guarded_coverage',
            'all_positive_widths': verified['status'] == 'certified', 'target_checked': True,
            'source_interface_verified': True, 'lean_checked': False,
            'target_sha256': compiled['target_sha256'], 'runtime': receipt, 'target': verified,
            'scope': 'restricted frontend, source/target semantics and Python checkers trusted; not new Lean verification'}


@dataclass(frozen=True, slots=True, init=False)
class VerifiedBundle:
    """Immutable process-local checked premise. Not restorable from a receipt."""
    _runner: object
    _model_json: str
    _payload_json: str
    _ir_json: str
    _receipt_json: str
    _results_json: str

    def __init__(self, key=None, **values):
        require(key is _KEY, 'use source-bound compact load')
        for name in self.__slots__: object.__setattr__(self, name, values[name])

    def __reduce_ex__(self, protocol):
        raise TypeError('export the certificate and recheck, not pickle')

    def results(self):
        return thaw(self._results_json)

    def value(self, raw, width):
        return self._runner.value(raw, width)

    def start(self):
        return self._runner.start()

    def explain_pair(self, left, right):
        payload = thaw(self._payload_json)
        obs = payload['source']['observations']
        witness, origin = finite.separator(Model(thaw(self._model_json)), obs, left, right)
        return {'schema': 'qkf-compact-separation-result-v1', 'status': 'separation_verified',
                'source_identity': thaw(self._receipt_json)['identity'], 'witness': witness,
                'question_origins': origin, 'each_representative_checked': True,
                'shortest_context_checked': False,
                'claim': 'these classes differ for this finite source consumer; not an upstream bug',
                'lean_checked': False}

    def check_obligation(self, target, obligation):
        """A fresh independently supplied target; no source reconstruction."""
        payload = thaw(self._payload_json)
        return check_target(thaw(self._ir_json), payload['selection'], self._runner,
                            thaw(self._receipt_json), thaw(freeze(target)), thaw(freeze(obligation)))

    def describe(self):
        return {'source': thaw(self._receipt_json), 'targets': len(thaw(self._results_json)),
                'stored_pair_witnesses': 0, 'proof_json_bytes': len(self._payload_json.encode()),
                'inspection_only': True}


def load(source, targets, packet):
    """Check the full shared premise once, then every supplied target obligation."""
    try:
        source = source_text(source)
        require(type(targets) is list and 0 < len(targets) <= 64, '1..64 independent targets')
        targets = thaw(freeze(targets))
        payload = dag.unpack(packet)
        require(type(payload) is dict and set(payload) == {'schema', 'selection', 'source', 'items'}
                and payload['schema'] == SCHEMA, 'compact target bundle')
        items = payload['items']
        require(type(items) is list and len(items) == len(targets), 'complete target list')
        for item, target in zip(items, targets):
            require(type(item) is dict and set(item) == {'target', 'obligation'}, 'target item fields')
            require(freeze(item['target']) == freeze(target), 'caller target substitution')
            require(freeze(prepare(target)[1]) == freeze(payload['selection']), 'one selected source')
        ir, model, runner, receipt = check_source(source, payload['selection'], payload['source'])
        results = [check_target(ir, payload['selection'], runner, receipt, t, p['obligation'])
                   for t, p in zip(targets, items)]
        return VerifiedBundle(_KEY, _runner=runner, _model_json=freeze(model.data),
            _payload_json=freeze(payload), _ir_json=freeze(ir),
            _receipt_json=freeze(receipt), _results_json=freeze(results))
    except Exception as exc:
        raise InvalidProof(str(exc)) from exc


def check(source, targets, packet):
    return load(source, targets, packet).results()


def export_legacy(source, targets, packet, index=0):
    """Explicit compatibility operation. Expands all source pair witnesses here ONLY.

    The old result/identity is recomputed, not copied from the new format. It
    preserves verdict, source, target, row action and obligation, not arbitrary
    original separator choices or byte identity of a supplied old certificate.
    """
    context = load(source, targets, packet)
    payload = thaw(context._payload_json)
    require(integer(index, 0, len(targets)-1), 'export target index')
    source_proof = payload['source']; obs = source_proof['observations']
    model = Model(thaw(context._model_json)); k = len(obs['blocks'])
    witnesses = [finite.separator(model, obs, i, j)[0] for i in range(k) for j in range(i+1, k)]
    obs.pop('separation'); obs['schema'] = ATOMIC_CERT_SCHEMA; obs['separators'] = witnesses
    source_proof['schema'] = OLD_SOURCE_SCHEMA
    from research.signed_coverage.runtime import load as old_load
    from research.signed_coverage import targets as old_targets
    from research.signed_context.session import wrap
    compiled, selection = prepare(targets[index])
    _, receipt = old_load(source, selection, source_proof)
    proof = {'schema': old_targets.SCHEMA, 'binding': old_targets.binding(compiled, receipt),
             'observations': source_proof, 'obligation': payload['items'][index]['obligation']}
    result = wrap(old_targets.check(source, targets[index], proof))
    require(result['status'] == context.results()[index]['status'], 'legacy export verdict differs')
    return {'schema': 'qkf-unified-proof-v5', 'kind': compiled['kind'], 'engine': old_targets.ENGINE,
            'proof': proof, 'result': result}
