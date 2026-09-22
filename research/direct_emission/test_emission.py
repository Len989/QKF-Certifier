"""PR49 wire attacks, actual emission boundaries, and unchanged replay contracts."""
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import FrozenInstanceError
import difflib
import hashlib
import json
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from research.applicable_summary import test_summary as previous_tests
from research.applicable_summary.checker import check
from research.applicable_summary.contract import canonical, digest
from research.signed_compact import dag
from research.prepared_context.values import plain
from research.prepared_context.checker import open_context
from .sdk import build
from .export import Assembler, Emission, slice_checked, _slice_ground


class EmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {c['name']: c for c in previous_tests.cases()}
        cls.built = {}
        for name in ('mask_all', 'parity_fixed8_reuse', 'empty', 'representation_gap', 'mask_refuted'):
            c = cls.cases[name]
            cls.built[name] = build(c['source'], c['request'], limits=c['limits'],
                                    policy='reuse' if name.endswith('reuse') else 'no_lemmas')
        cls.case = cls.cases['mask_all']
        cls.packet, cls.result, cls.work = cls.built['mask_all']

    checked = previous_tests.Summary.checked
    invalid = previous_tests.Summary.invalid

    def test_preregistered_population_and_source_provenance(self):
        from .common import registered, validate_case
        from .fixtures import cases
        from research.sdk_comparison.fixtures import cases as old_cases
        protocol, reg = registered()
        self.assertEqual((len(reg['cases']), sum(len(c['routes']) for c in reg['cases'])), (6, 48))
        originals = {c['name']: c for c in old_cases()}
        for c, row in zip(cases(), reg['cases']):
            validate_case(c, row)
            for key in ('source', 'request', 'limits', 'applications', 'followups'):
                self.assertEqual(c[key], originals[c['pr47_case']][key])
        here = Path(__file__).parent
        adaptation = json.loads((here / 'ADAPTATION.json').read_text())
        source = Path(adaptation['source']).read_text()
        adapter = Path(adaptation['adapter']).read_text()
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), adaptation['source_sha256'])
        self.assertEqual(list(difflib.unified_diff(source.splitlines(True), adapter.splitlines(True),
                         fromfile='PR48', tofile='PR49')), adaptation['patch'])

    def test_all_signed_cases_four_factors(self):
        from research.sdk_comparison.fixtures import cases
        count = 0
        for c in cases():
            if c['group'] == 'phase':
                continue
            count += 1
            for backend in ('ordinary', 'query'):
                for policy in ('no_lemmas', 'reuse'):
                    with self.subTest(case=c['name'], backend=backend, policy=policy):
                        packet, result, work = build(c['source'], c['request'], backend=backend,
                                                     policy=policy, limits=c['limits'])
                        self.assertEqual(result['status'], next(iter(c['expected'].values())))
                        if packet and result['status'] == 'certified':
                            self.assertEqual(work['backend']['emission']['intermediate_native_packets'], 0)
        self.assertEqual(count, 27)

    def test_matched_packets_results_questions_and_checkpoint_ids(self):
        from research.prepared_context.sdk import build as previous
        from .fixtures import cases
        for c in cases():
            if c['shard'] == 'each':
                continue  # Fresh independent members are measured by the registered harness.
            factors = [('query', 'no_lemmas')] if c['shard'] == 'fallback' else [
                (b, p) for b in ('ordinary', 'query') for p in ('no_lemmas', 'reuse')]
            for backend, policy in factors:
                with self.subTest(case=c['name'], backend=backend, policy=policy):
                    args = dict(backend=backend, policy=policy, limits=c['limits'])
                    new = build(c['source'], c['request'], **args)
                    old = previous(c['source'], c['request'], **args)
                    self.assertEqual(canonical(list(new[:2])), canonical(list(old[:2])))
                    for key in ('fact_attempts', 'foundations'):
                        self.assertEqual(new[2]['backend'][key], old[2]['backend'][key])
                    self.assertEqual([r['id'] for r in new[2]['backend']['checkpoints']],
                                     [r['id'] for r in old[2]['backend']['checkpoints']])

    def test_positive_has_one_final_pack_and_public_check(self):
        from research.applicable_summary.contract import PACKET
        from research.applicable_summary.checker import components
        original = dag.pack
        schemas = []
        def packing(value):
            schemas.append(value.get('schema'))
            return original(value)
        c = self.cases['parity_fixed8_reuse']
        with ExitStack() as stack:
            for target in ('research.applicable_summary.export.extract', 'research.applicable_summary.checker.package',
                           'research.direct_emission.producer.check'):
                stack.enter_context(patch(target, side_effect=AssertionError('redundant positive stage: ' + target)))
            packed = stack.enter_context(patch('research.direct_emission.sdk.dag.pack', side_effect=packing))
            cold = stack.enter_context(patch('research.applicable_summary.checker.check', wraps=check))
            replay = stack.enter_context(patch('research.applicable_summary.checker.components', wraps=components))
            packet, result, work = build(c['source'], c['request'], policy='reuse')
        self.assertEqual(result['status'], 'certified')
        self.assertEqual(schemas, [PACKET])
        self.assertEqual((packed.call_count, cold.call_count, replay.call_count), (1, 1, 1))
        self.assertEqual(work['backend']['emission']['intermediate_native_packet_bytes'], 0)

    def test_final_serialization_corruption_rejected_inside_build(self):
        original = dag.pack
        def damaged(value):
            data = deepcopy(value)
            data['interface']['values'][0] = not data['interface']['values'][0]
            return original(data)
        c = self.case
        with patch('research.direct_emission.sdk.dag.pack', side_effect=damaged):
            with self.assertRaisesRegex(ValueError, 'execution form differs'):
                build(c['source'], c['request'])

    def test_fallback_retains_models_and_actual_history(self):
        c = self.cases['representation_gap']
        packet, result, work = self.built[c['name']]
        data = dag.unpack(packet)
        self.assertEqual(data['kind'], 'native_batch')
        self.assertTrue(any(r['item'].get('certificate', {}).get('models') for r in work['backend']['checkpoints']))
        self.assertEqual(work['backend']['emission']['intermediate_native_packets'], 1)
        from research.sdk_comparison.verify import history_check
        checked = history_check(c, [(c['request'], 'emitted_query_no_lemmas')], [work])
        self.assertEqual(checked, len(work['backend']['checkpoints']))

    def test_mixed_positive_inactive_batch_keeps_full_fallback(self):
        c = deepcopy(self.case)
        first = self.work['backend']['checkpoints'][-1]['item']['certificate']['horizon']
        other = deepcopy(c['request']['query']['requests'][0])
        for _ in range(first + 4):
            other['target']['goal'] = ['not', other['target']['goal']]
        c['request']['query']['requests'].append(other)
        packet, result, work = build(c['source'], c['request'], limits=dict(max_horizon=first))
        self.assertEqual([g['status'] for g in result['goals']], ['certified', 'unresolved'])
        self.assertEqual(dag.unpack(packet)['kind'], 'native_batch')
        self.assertGreater(work['backend']['emission']['nodes_created'], 0)
        self.assertEqual(check(c['source'], c['request'], packet).result(), result)

    def test_no_receipts_foreign_or_mutable_emission(self):
        from .producer import prove
        c = self.case
        emitted, result, work = prove(c['source'], c['request']['query'])
        self.assertIs(type(emitted), Emission)
        with self.assertRaises(ValueError): Emission(evidence={}, checked=True)
        with self.assertRaises(TypeError): pickle.dumps(emitted)
        with self.assertRaises(FrozenInstanceError): emitted.evidence = {}
        with self.assertRaises(TypeError): emitted.evidence['nodes'][0]['id'] = 'fake'
        wire = plain(emitted.evidence); wire['nodes'].clear()
        self.assertTrue(emitted.evidence['nodes'])
        p, _ = open_context(c['source'], c['request']['query'])
        a = Assembler(p)
        with self.assertRaises(ValueError): a.goal(dict(checked=True))
        with self.assertRaises(ValueError): slice_checked(dict(checked=True))
        foreign, _ = open_context(c['source'], c['request']['query'])
        foreign = foreign.add_native(work['foundations']['E'][0])
        with self.assertRaises(ValueError): a.native(foreign)
        with self.assertRaises(ValueError): a.native(p)
        with self.assertRaises(ValueError): a.cached(True)

    def test_lemma_endpoint_swap_and_false_residual_with_valid_ground_proof(self):
        def endpoint(d):
            n = next(n for n in d['evidence']['nodes'] if n.get('via') is not None)
            n['claim'][0] = ['b.true']
        self.invalid(endpoint, 'parity_fixed8_reuse')
        def residual(d):
            from research.source_query.ordinary import prove
            from research.ground_query.checker import check as ground_check
            n = next(n for n in d['evidence']['nodes'] if n.get('via') is not None)
            a, b = n['request']['queries'][0]
            n['request']['queries'][0] = [a, a]
            n['request']['queries'].append([b, b])
            n['proof'], _ = prove(n['request'])
            self.assertEqual(ground_check(n['request'], n['proof'])['goals'][0]['status'], 'equal')
        self.invalid(residual, 'parity_fixed8_reuse')

    def test_missing_native_proof_with_repaired_identity(self):
        def change(d):
            n = next(n for n in d['evidence']['nodes'] if n['kind'] == 'native')
            n['entry']['evidence'] = {}
        self.invalid(change)

    def test_fresh_normal_optimized_replay_includes_every_checkpoint(self):
        from .worker import run
        from .fixtures import cases
        c = next(c for c in cases() if c['shard'] == 'mask')
        route = 'emitted_query_reuse'
        saved = run(c, route, audit=True)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, data in [('case', c), ('saved', saved)]:
                (root / (name + '.json')).write_text(json.dumps(data))
            results = []
            for flags in ([], ['-O']):
                output = root / ('check-' + str(len(flags)) + '.json')
                proc = subprocess.run([sys.executable, *flags, '-m', 'research.direct_emission.verify',
                    str(root/'case.json'), route, str(root/'saved.json'), str(output), '--history'],
                    capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                results.append(json.loads(output.read_text()))
            self.assertEqual(results[0]['semantic'], results[1]['semantic'])
            self.assertEqual(results[0]['checkpoints'], len(saved['work']['members'][0]['backend']['checkpoints']))
            self.assertEqual(results[0]['search_imports'], 0)

    def test_historical_workflow_changes_only_triggers_and_explicit_gate(self):
        from .preserve import BASE, audit
        audit()
        for filename in ('sdk-cost-contracts.yml', 'prepared-context.yml'):
            path = '.github/workflows/' + filename
            old = subprocess.check_output(['git', 'show', BASE + ':' + path], text=True)
            new = Path(path).read_text()
            start, end = new.index('    paths:\n'), new.index('  workflow_dispatch:')
            normalized = new[:start] + new[end:]
            if filename == 'prepared-context.yml':
                normalized = normalized.replace('research.direct_emission.preserve', 'research.prepared_context.preserve')
            self.assertEqual(normalized, old)

    def test_used_congruence_terms_survive_pruning_without_new_axioms(self):
        from research.source_lemmas.context import prepare
        from research.source_query.encoding import Graph
        from research.source_lemmas.terms import term
        from research.ground_query.schema import parse, PROOF_SCHEMA
        from research.ground_query.checker import check as ground_check
        from research.prepared_context.ground import admit
        ctx, _ = prepare(self.case['source'], self.case['request']['query'])
        g = Graph(ctx)
        a,b,c = [g.node('t.'+s) for s in ('negative','nonnegative','popcount_eq.0')]
        fa,fb,fc = [g.node('b.not', v) for v in (a,b,c)]
        req,_ = g.finish([(a,b),(b,c),(fb,fb)], (fa,fc), [])
        g = Graph(ctx,req); a,b,c = [g.node('t.'+s) for s in ('negative','nonnegative','popcount_eq.0')]
        fa,fb,fc = [g.node('b.not', v) for v in (a,b,c)]
        events = [dict(rule='axiom',left=a,right=b,depth=0,equation=0),dict(rule='axiom',left=b,right=c,depth=0,equation=1),
                  dict(rule='congruence',left=fa,right=fb,depth=1,premises=[[0]]),dict(rule='congruence',left=fb,right=fc,depth=1,premises=[[1]])]
        proof=dict(schema=PROOF_SCHEMA,request_sha256=parse(req).identity,mode='entailment',horizon=1,
                   events=events,models=[],goals=[dict(status='equal',path=[2,3],depth=1,lower_model=None)])
        ground_check(req,proof)
        premises = [[term(g,x),term(g,y)] for x,y in parse(req).equations]
        new, cert, used = _slice_ground(admit(req),proof)
        self.assertEqual(used,[0,1]); self.assertEqual(len(new['equations']),2)
        self.assertEqual(len(new['queries']),2); self.assertEqual(new['queries'][1][0],new['queries'][1][1])
        self.assertEqual(ground_check(new,cert)['goals'][0]['status'],'equal')


# Exercise the established attack contract against packets built by PR49.
# Reuse only tests that consume self.built/self.invalid, never the old builder.
for name in (
    'positive_check_never_evaluates_the_source', 'direct_certificate_slices_unneeded_native_facts',
    'wrong_concrete_witness_rejected', 'empty_cannot_replace_positive_proof',
    'interface_value_tamper_rejected', 'interface_scope_tamper_rejected', 'interface_coverage_tamper_rejected',
    'foreign_source_hash_repair_does_not_transfer_proof', 'independent_request_rebinding_rejected',
    'guard_and_width_rebinding_rejected', 'fake_native_fact_with_repaired_ids_rejected',
    'missing_foundation_rejected', 'orphan_valid_foundation_rejected', 'forward_dependency_rejected',
    'self_dependency_rejected', 'duplicate_dependency_rejected', 'false_claim_with_repaired_ids_rejected',
    'dropping_transitive_source_lemma_rejected', 'corrupted_ground_path_rejected',
    'auxiliary_query_cannot_add_a_new_claim', 'extra_equation_cannot_become_a_free_assumption',
    'missing_consumer_rejected', 'cached_goal_cannot_look_forward'):
    setattr(EmissionTests, 'test_' + name, getattr(previous_tests.Summary, 'test_' + name))


if __name__ == '__main__':
    unittest.main()
