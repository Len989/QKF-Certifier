"""Contract, adversarial certificates and source-free application checks."""
import copy
import json
import pickle
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from research.signed_compact import dag
from .contract import (SIGNED, PHASE, canonical, digest, request, signed_request,
                       phase_request, load_json, save_json, Unsupported)
from .fixtures import cases, MASK, PARITY, target, goals
from .producer import build, refine
from .checker import check, from_certificate
from .runtime import CheckedSummary, NotApplicable, OutsideDomain
from .audit import ExecutionGuard


def reidentify(data):
    """Repair superficial content IDs; soundness must still reject false evidence."""
    renamed = {}
    def replace(x):
        if type(x) is str:
            return renamed.get(x, x)
        if type(x) is list:
            return [replace(v) for v in x]
        if type(x) is dict:
            return {k: replace(v) for k, v in x.items()}
        return x
    for i, node in enumerate(data['evidence']['nodes']):
        old = node['id']
        body = replace({k: v for k, v in node.items() if k != 'id'})
        if body['kind'] == 'native':
            entry = body['entry']
            entry['id'] = digest({k: v for k, v in entry.items() if k != 'id'})
        renamed[old] = digest(body)
        data['evidence']['nodes'][i] = dict(id=renamed[old], **body)
    data['evidence']['goals'] = replace(data['evidence']['goals'])
    return data


class Summary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {c['name']: c for c in cases()}
        cls.built = {}
        for name in ('mask_all', 'parity_fixed8_reuse', 'phase_direct', 'empty', 'representation_gap', 'mask_refuted'):
            c = cls.cases[name]
            cls.built[name] = build(c['source'], c['request'], route=c['route'], limits=c['limits'])
        cls.case = cls.cases['mask_all']
        cls.packet, cls.result, cls.work = cls.built['mask_all']

    def checked(self, name='mask_all'):
        c = self.cases[name]
        return check(c['source'], c['request'], self.built[name][0])

    def invalid(self, change, name='mask_all', repair=True):
        c, packet = self.cases[name], self.built[name][0]
        data = dag.unpack(packet)
        change(data)
        if repair and data['kind'] == 'native_direct':
            reidentify(data)
        with self.assertRaises((ValueError, TypeError, KeyError, IndexError)):
            check(c['source'], c['request'], dag.pack(data))

    def test_registration_is_unchanged(self):
        reg = load_json(Path(__file__).with_name('REGISTRATION.json'))
        protocol = load_json(Path(__file__).with_name('PROTOCOL.json'))
        self.assertEqual(digest(protocol), reg['protocol_sha256'])
        self.assertEqual([(c['name'], digest(c), c['expected']) for c in cases()],
                         [(c['name'], c['case_sha256'], c['expected']) for c in reg['cases']])

    def test_sdk_can_be_called_repeatedly(self):
        from research import applicable_summary as sdk
        c = self.cases['empty']
        for _ in range(2):
            packet, result, _ = sdk.build(c['source'], c['request'])
            self.assertEqual(sdk.check(c['source'], c['request'], packet).result(), result)

    def test_default_respects_A1_A2(self):
        self.assertEqual(self.work['backend']['route'], 'no_lemmas')
        self.assertEqual(dag.unpack(self.built['phase_direct'][0])['evidence']['kind'], 'direct_cell')

    def test_direct_certificate_slices_unneeded_native_facts(self):
        data = dag.unpack(self.packet)
        self.assertEqual(data['kind'], 'native_direct')
        stats = self.work['extraction']
        self.assertLess(stats['native_retained'], stats['native_available'])
        self.assertTrue(all(n['kind'] in ('native', 'equality') for n in data['evidence']['nodes']))

    def test_positive_check_never_evaluates_the_source(self):
        with ExecutionGuard(checking=True):
            self.assertEqual(self.checked().result()['status'], 'certified')

    def test_actual_call_guard_rejects_preloaded_source_execution(self):
        namespace = {'__name__': 'research.signed_predicates.semantics'}
        exec('def evaluate(): return True', namespace)
        with ExecutionGuard(checking=True), self.assertRaises(RuntimeError):
            namespace['evaluate']()

    def test_actual_call_guard_rejects_hidden_full_legacy_builder(self):
        namespace = {'__name__': 'research.legacy'}
        exec('def source_quotient(): return {}', namespace)
        with patch('research.applicable_summary.export.extract', side_effect=lambda *a: namespace['source_quotient']()):
            with self.assertRaisesRegex(RuntimeError, 'source_quotient'):
                build(self.case['source'], self.case['request'])

    def test_checked_apply_matches_concrete_semantics_on_guarded_words(self):
        from research.source_query.context import prepare
        from research.signed_predicates.semantics import evaluate
        from research.signed_predicates.frontend import target_value
        for name, widths in [('mask_all', range(1, 7)), ('parity_fixed8_reuse', [8])]:
            c, checked = self.cases[name], self.checked(name)
            q = c['request']['query']['requests'][0]
            ctx = prepare(c['source'], q)
            for w in widths:
                for value in range(1 << w):
                    if all(target_value(g, value.bit_count(), value >> (w - 1)) for g in q['guards']):
                        self.assertEqual(checked.apply(value, width=w), evaluate(ctx.ir, value, w))

    def test_warm_apply_assess_explain_do_not_parse_or_execute_source(self):
        checked = self.checked()
        consumer = signed_request(target(['not', ['nonnegative']]), guards=[['popcount_le', 1]])
        with ExecutionGuard(checking=True, application=True), patch(
                'research.signed_bridge.model.read', side_effect=AssertionError('source read')):
            self.assertIs(checked.apply(128, width=8), True)
            self.assertEqual(checked.assess(consumer)['status'], 'certified')
            self.assertEqual(checked.explain(consumer=consumer)['sufficiency']['basis_goal'], 0)

    def test_large_runtime_width_is_explicit_and_supported(self):
        self.assertIs(self.checked().apply(1 << 4095, width=4096), True)

    def test_runtime_guard_violation_is_rejected(self):
        with self.assertRaises(OutsideDomain):
            self.checked().apply(3, width=8)

    def test_runtime_fixed_width_violation_is_rejected(self):
        with self.assertRaises(OutsideDomain):
            self.checked('parity_fixed8_reuse').apply(1, width=1)

    def test_runtime_input_and_width_types(self):
        checked = self.checked()
        for value, width in [(True, 8), (-1, 8), (256, 8), (0, True), (0, 0), (0, None), (0, 4097)]:
            with self.subTest(value=value, width=width), self.assertRaises(ValueError):
                checked.apply(value, width=width)

    def test_new_equivalent_consumer_needs_no_planner(self):
        r = signed_request(target(['and', ['not', ['nonnegative']], ['popcount_le', 1]]), guards=[['popcount_le', 1]])
        outcome = self.checked().assess(r)
        self.assertEqual(outcome['status'], 'certified')
        self.assertFalse(outcome['refinement_required'])

    def test_new_nonmatching_consumer_requests_refinement_not_refutation(self):
        r = signed_request(target(['nonnegative']), guards=[['popcount_le', 1]])
        outcome = self.checked().assess(r)
        self.assertEqual(outcome['status'], 'unresolved')
        self.assertTrue(outcome['refinement_required'])

    def test_sufficiency_refuses_changed_guard_width_or_selection(self):
        original = self.case['request']
        for which in ('guard', 'width', 'selection'):
            r = copy.deepcopy(original)
            q = r['query']['requests'][0]
            if which == 'guard': q['guards'] = []
            elif which == 'width': q['width'] = dict(kind='fixed', bits=8)
            else: q['target']['source']['entry']['method'] = 'other'
            self.assertEqual(self.checked().assess(r)['reason'], 'different_selection_guard_or_width')

    def test_sufficiency_does_not_cross_profiles(self):
        self.assertEqual(self.checked().assess(phase_request([0,1,1,0], [[3,0]]))['status'], 'unresolved')

    def test_unsupported_target_does_not_alias_capped_count(self):
        r = copy.deepcopy(self.case['request'])
        r['query']['requests'][0]['target']['goal'] = ['popcount_eq', 4]
        with self.assertRaises(ValueError):
            self.checked().assess(r)

    def test_explicit_refinement_checks_the_new_goal(self):
        r = signed_request(target(['nonnegative']), guards=[['popcount_le', 1]])
        packet, result, _ = refine(self.case['source'], self.checked(), r)
        self.assertEqual(result['status'], 'refuted')
        self.assertEqual(check(self.case['source'], r, packet).result(), result)

    def test_refinement_does_not_transport_changed_source(self):
        with self.assertRaises(ValueError):
            refine(self.case['source'] + '\n', self.checked(), self.case['request'])

    def test_receipt_cannot_issue_summary(self):
        with self.assertRaises(ValueError):
            CheckedSummary(**self.result)

    def test_checked_summary_is_immutable_and_unpickleable(self):
        checked = self.checked()
        with self.assertRaises((AttributeError, TypeError)):
            checked._action = '{}'
        with self.assertRaises(TypeError):
            pickle.dumps(checked)
        action = checked.interface(); action['values'][0] = not action['values'][0]
        result = checked.result(); result['status'] = 'refuted'
        exported = checked.export(); exported['root'] = 0
        self.assertIs(checked.apply(0, width=8), False)
        self.assertEqual(checked.result()['status'], 'certified')

    def test_explanation_contains_transitive_checked_dependencies(self):
        explanation = self.checked('parity_fixed8_reuse').explain(1)['dependencies']
        self.assertEqual(explanation['kind'], 'direct_dependencies')
        self.assertTrue(any(n['kind'] == 'native' for n in explanation['nodes']))
        self.assertTrue(any(n.get('via') is not None for n in explanation['nodes']))
        self.assertIn(explanation['root'], [n['id'] for n in explanation['nodes']])

    def test_empty_domain_is_not_a_useful_action(self):
        checked = self.checked('empty')
        self.assertEqual(checked.result()['status'], 'verified_empty_domain')
        self.assertFalse(checked.result()['applicable'])
        with self.assertRaises(OutsideDomain): checked.apply(0, width=8)

    def test_unresolved_lower_model_is_not_executable(self):
        checked = self.checked('representation_gap')
        self.assertEqual(dag.unpack(checked.export())['kind'], 'native_batch')
        self.assertEqual(checked.result()['status'], 'unresolved')
        with self.assertRaises(NotApplicable): checked.apply(1, width=8)

    def test_refutation_recomputes_concrete_source_witness(self):
        with ExecutionGuard(checking=True, witness=True):
            checked = self.checked('mask_refuted')
        witness = checked.result()['goals'][0]['witness']
        self.assertTrue(witness['guard_satisfied'])
        self.assertNotEqual(witness['source_value'], witness['target_value'])
        with self.assertRaises(RuntimeError):
            with ExecutionGuard(checking=True): self.checked('mask_refuted')

    def test_refuted_goal_does_not_issue_an_action(self):
        with self.assertRaises(NotApplicable): self.checked('mask_refuted').apply(128, width=8)

    def test_wrong_concrete_witness_rejected(self):
        def change(d): d['evidence']['goals'][0]['certificate']['evidence']['input'] = 3
        self.invalid(change, 'mask_refuted')

    def test_empty_cannot_replace_positive_proof(self):
        self.invalid(lambda d: d['evidence']['goals'].__setitem__(0, dict(kind='empty')))

    def test_interface_value_tamper_rejected(self):
        self.invalid(lambda d: d['interface']['values'].__setitem__(0, not d['interface']['values'][0]))

    def test_interface_scope_tamper_rejected(self):
        for key, value in [('count_cap', 3), ('guards', []), ('width', dict(kind='fixed', bits=1)), ('basis_goal', True)]:
            with self.subTest(key=key): self.invalid(lambda d: d['interface'].__setitem__(key, value))

    def test_interface_coverage_tamper_rejected(self):
        self.invalid(lambda d: d['interface']['states'].pop())

    def test_untrusted_receipt_is_not_evidence(self):
        self.invalid(lambda d: d.__setitem__('evidence', self.result), repair=False)

    def test_foreign_source_hash_repair_does_not_transfer_proof(self):
        source = self.case['source'].replace('(x&7)==0', '(x&7)==1')
        import hashlib
        data = dag.unpack(self.packet); data['source_sha256'] = hashlib.sha256(source.encode()).hexdigest()
        with self.assertRaises(ValueError): check(source, self.case['request'], dag.pack(data))

    def test_independent_request_rebinding_rejected(self):
        r = copy.deepcopy(self.case['request']); r['query']['requests'][0]['target']['goal'] = ['nonnegative']
        with self.assertRaises(ValueError): check(self.case['source'], r, self.packet)
        data = dag.unpack(self.packet); data['request'] = r
        with self.assertRaises(ValueError): check(self.case['source'], r, dag.pack(data))

    def test_guard_and_width_rebinding_rejected(self):
        for field, value in [('guards', []), ('width', dict(kind='fixed', bits=8))]:
            r = copy.deepcopy(self.case['request']); r['query']['requests'][0][field] = value
            d = dag.unpack(self.packet); d['request'] = r
            with self.assertRaises(ValueError): check(self.case['source'], r, dag.pack(d))

    def test_boolean_integer_alias_in_request_rejected(self):
        for field, value in [('guards', [['popcount_le', True]]), ('width', dict(kind='fixed', bits=True))]:
            r = copy.deepcopy(self.case['request']); r['query']['requests'][0][field] = value
            with self.assertRaises(ValueError): request(r)

    def test_bad_schema_or_extra_field_rejected(self):
        self.invalid(lambda d: d.__setitem__('schema', 'qkf-applicable-summary-v999'))
        self.invalid(lambda d: d.__setitem__('trusted', True))

    def test_profile_kind_confusion_rejected(self):
        self.invalid(lambda d: d.__setitem__('kind', 'phase_cell'))

    def test_fake_native_fact_with_repaired_ids_rejected(self):
        def change(d):
            n = next(n for n in d['evidence']['nodes'] if n['kind'] == 'native')
            n['entry']['claim'][1] = ['b.false']
        self.invalid(change)

    def test_native_algebra_rebinding_rejected(self):
        self.invalid(lambda d: d['evidence']['scope'].__setitem__('guarantee', 'universal_schema'))

    def test_missing_foundation_rejected(self):
        self.invalid(lambda d: d['evidence']['nodes'].pop(0))

    def test_orphan_valid_foundation_rejected(self):
        data = dag.unpack(self.packet)
        kept = {n['entry']['id'] for n in data['evidence']['nodes'] if n['kind'] == 'native'}
        extra = next(e for e in self.work['backend']['foundations']['E'] if e['id'] not in kept)
        self.invalid(lambda d: d['evidence']['nodes'].append(dict(id='temporary', kind='native', entry=extra)))

    def test_forward_dependency_rejected(self):
        self.invalid(lambda d: d['evidence']['nodes'].reverse())

    def test_self_dependency_rejected(self):
        def change(d):
            n = next(n for n in d['evidence']['nodes'] if n['kind'] == 'equality')
            n['premises'] = [n['id']]
        self.invalid(change)

    def test_duplicate_dependency_rejected(self):
        self.invalid(lambda d: d['evidence']['nodes'].append(copy.deepcopy(d['evidence']['nodes'][0])))

    def test_false_claim_with_repaired_ids_rejected(self):
        def change(d):
            n = next(n for n in reversed(d['evidence']['nodes']) if n['kind'] == 'equality')
            n['claim'][1] = ['b.false']
        self.invalid(change)

    def test_dropping_transitive_source_lemma_rejected(self):
        def change(d):
            n = next(n for n in d['evidence']['nodes'] if n.get('via') is not None)
            n['via'] = None
        self.invalid(change, 'parity_fixed8_reuse')

    def test_corrupted_ground_path_rejected(self):
        def change(d):
            n = next(n for n in d['evidence']['nodes'] if n['kind'] == 'equality')
            n['proof']['goals'][0]['path'] = []
        self.invalid(change)

    def test_auxiliary_query_cannot_add_a_new_claim(self):
        from research.ground_query.schema import parse
        def change(d):
            n = next(n for n in d['evidence']['nodes'] if n['kind'] == 'equality')
            n['request']['queries'].append(copy.deepcopy(n['request']['queries'][0]))
            n['proof']['request_sha256'] = parse(n['request']).identity
            n['proof']['goals'].append(copy.deepcopy(n['proof']['goals'][0]))
        self.invalid(change)

    def test_extra_equation_cannot_become_a_free_assumption(self):
        from research.ground_query.schema import parse
        def change(d):
            n = next(n for n in d['evidence']['nodes'] if n['kind'] == 'equality')
            n['request']['equations'].append(copy.deepcopy(n['request']['queries'][0]))
            n['proof']['request_sha256'] = parse(n['request']).identity
        self.invalid(change)

    def test_missing_consumer_rejected(self):
        self.invalid(lambda d: d['evidence']['goals'].pop())

    def test_cached_goal_cannot_look_forward(self):
        self.invalid(lambda d: d['evidence']['goals'].__setitem__(0, dict(kind='cached', previous=0)))

    def test_exact_goal_cache_roundtrip(self):
        r = signed_request([target(['negative'])] * 2, guards=[['popcount_le', 1]])
        packet, result, _ = build(MASK, r)
        self.assertEqual(dag.unpack(packet)['evidence']['goals'][1], dict(kind='cached', previous=0))
        self.assertEqual(check(MASK, r, packet).result()['goals'][0], result['goals'][1])

    def test_phase_action_has_only_checked_cells(self):
        checked = self.checked('phase_direct')
        with ExecutionGuard(checking=True, application=True): self.assertEqual(checked.apply(3), 0)
        with self.assertRaises(NotApplicable): checked.apply(7)
        with self.assertRaises(ValueError): checked.apply(3, width=8)
        self.assertEqual(checked.assess(phase_request([0,1,1,0], [[3,0]]))['status'], 'certified')
        self.assertTrue(checked.assess(phase_request([0,1,1,0], [[7,5]]))['refinement_required'])

    def test_phase_label_and_value_tampering_rejected(self):
        self.invalid(lambda d: d['interface']['label'].__setitem__(3, 1), 'phase_direct', repair=False)
        self.invalid(lambda d: d['interface']['cells'][0].__setitem__(1, 1), 'phase_direct', repair=False)

    def test_budget_and_unsupported_have_no_partial_summary(self):
        for name in ('budget', 'unsupported'):
            c = self.cases[name]
            packet, result, _ = build(c['source'], c['request'], limits=c['limits'])
            self.assertIsNone(packet); self.assertFalse(result['applicable']); self.assertEqual(result['goals'], [])
            self.assertEqual(result['status'], c['expected'])

    def test_dag_cycle_rejected(self):
        p = copy.deepcopy(self.packet)
        p['nodes'][p['root']] = ['l', [p['root']]]
        with self.assertRaises(ValueError): check(self.case['source'], self.case['request'], p)

    def test_strict_json_duplicate_key_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'bad.json'; p.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError): load_json(p)

    def test_fresh_normal_and_optimized_check_apply_without_search(self):
        script = '''import sys
from research.applicable_summary.replay import NoSearch
guard=NoSearch(); sys.meta_path.insert(0,guard)
from research.applicable_summary.contract import load_json
from research.applicable_summary.checker import check
from research.applicable_summary.audit import ExecutionGuard
from pathlib import Path
p=Path(sys.argv[1]); c=load_json(p/'case.json')
with ExecutionGuard(checking=True):
 s=check(c['source'],c['request'],load_json(p/'packet.json'))
with ExecutionGuard(checking=True,application=True):
 if s.apply(128,width=8) is not True: raise RuntimeError('apply')
 s.explain()
if guard.loaded(): raise RuntimeError(guard.loaded())
print('checked-and-applied')
'''
        with tempfile.TemporaryDirectory() as td:
            p = Path(td); save_json(p/'case.json', self.case); save_json(p/'packet.json', self.packet)
            for flags in ([], ['-O']):
                r = subprocess.run([sys.executable, *flags, '-c', script, str(p)], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual(r.stdout.strip(), 'checked-and-applied')

    def test_cli_check_apply_assess_explain_and_exclusive_build(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td); (p/'source.java').write_text(self.case['source'])
            save_json(p/'request.json', self.case['request']); save_json(p/'proof.json', self.packet)
            def command(op, *flags):
                return subprocess.run([sys.executable, '-m', 'research.applicable_summary', op, str(p/'source.java'),
                    '--request', str(p/'request.json'), '--proof', str(p/'proof.json'), *flags], capture_output=True, text=True)
            for op, flags in [('check', []), ('apply', ['--input','128','--width','8']),
                              ('explain', []), ('assess', ['--consumer',str(p/'request.json')])]:
                result = command(op, *flags); self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                json.loads(result.stdout)
            result = command('build'); self.assertEqual(result.returncode, 2)
            self.assertEqual(load_json(p/'proof.json'), self.packet)

    def test_used_congruence_terms_survive_pruning_without_new_axioms(self):
        from research.source_lemmas.context import prepare
        from research.source_query.encoding import Graph
        from research.source_lemmas.terms import term
        from research.ground_query.schema import parse, PROOF_SCHEMA
        from research.ground_query.checker import check as ground_check
        from .export import slice_ground
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
        new, cert, used = slice_ground(ctx,req,proof,premises,[term(g,fa),term(g,fc)])
        self.assertEqual(used,[0,1]); self.assertEqual(len(new['equations']),2)
        self.assertEqual(len(new['queries']),2); self.assertEqual(new['queries'][1][0],new['queries'][1][1])
        self.assertEqual(ground_check(new,cert)['goals'][0]['status'],'equal')


if __name__ == '__main__':
    unittest.main()
