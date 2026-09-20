from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from .context import prepare, digest, make_request, save_json
from .fixtures import cases, target, TRUE, FALSE
from .producer import prove
from .checker import check, envelope
from .encoding import Graph
from .rules import check_fact, guard_truth
from .audit import Audit, limits, ForbiddenConstruction
from research.signed_predicates.semantics import evaluate
from research.signed_predicates.frontend import target_value

CASES = {c['name']: c for c in cases()}


class SourceQueryTests(unittest.TestCase):
    def proof(self, name='mask_31', **kwargs):
        c = deepcopy(CASES[name])
        p, r, w = prove(c['source'], c['request'], fallback=c['fallback'], limits=c['limits'], **kwargs)
        return c, p, r, w

    def reject(self, name, change):
        c, p, _, _ = self.proof(name)
        change(c, p)
        with self.assertRaises((ValueError, TypeError, KeyError)):
            check(c['source'], c['request'], p)

    def test_registered_population(self):
        registered = json.loads(Path(__file__).with_name('REGISTRATION.json').read_text())
        self.assertEqual(len(CASES), 32)
        self.assertEqual(registered['cases'], [{'name': c['name'], 'family': c['family'],
                         'expected': c['expected'], 'case_sha256': digest(c)} for c in cases()])

    def test_all_cases_and_fair_control(self):
        for name, c in CASES.items():
            hashes, statuses = [], []
            for route in ('query', 'ordinary'):
                with self.subTest(name=name, route=route):
                    _, p, r, w = self.proof(name, route=route)
                    self.assertEqual(r['status'], c['expected'])
                    if p is not None:
                        self.assertEqual(check(c['source'], c['request'], p), r)
                    hashes.append(w['ground_request_sha256'])
                    statuses.append(r['status'])
            self.assertEqual(hashes[0], hashes[1])
            self.assertEqual(statuses[0], statuses[1])

    def test_new_positives_do_not_construct_legacy_models(self):
        for name in ('mask_31', 'mask_61', 'mask_guard_zero', 'double_even', 'renamed_nested'):
            _, p, r, w = self.proof(name)
            self.assertEqual(p['kind'], 'ground')
            self.assertEqual(w['counts'].get('legacy_builder_calls', 0), 0)
            self.assertEqual(w['counts'].get('witness_source_evaluations', 0), 0)
            self.assertEqual(r['status'], 'certified')

    def test_actual_builder_calls_are_forbidden(self):
        from research.signed_coverage.producer import infer
        ctx = prepare(CASES['mask_31']['source'], CASES['mask_31']['request'])
        with self.assertRaises(ForbiddenConstruction):
            with Audit(limits({})):
                infer(CASES['mask_31']['source'], ctx.selection)

    def test_new_proof_needs_ground_congruence(self):
        _, p, _, _ = self.proof('arithmetic_compound')
        self.assertTrue(any(e['rule'] == 'congruence' for e in p['evidence']['certificate']['events']))

    def test_source_tamper(self):
        self.reject('mask_31', lambda c, p: c.update(source=c['source'].replace('2147483648L', '2147483649L')))

    def test_guard_tamper(self):
        self.reject('signed_guard', lambda c, p: c['request'].update(guards=[['negative']]))

    def test_width_tamper(self):
        self.reject('mask_fixed_alias', lambda c, p: c['request'].update(width={'kind': 'fixed', 'bits': 2}))

    def test_fixed_proof_cannot_become_all_widths(self):
        self.reject('mask_fixed_alias', lambda c, p: c['request'].update(width={'kind': 'all_positive'}))

    def test_fixed_native_rule_rejected_after_scope_rebinding(self):
        def change(c, p):
            c['request']['width'] = {'kind': 'all_positive'}
            p['binding'] = prepare(c['source'], c['request']).binding()
        self.reject('mask_fixed_alias', change)

    def test_target_tamper(self):
        self.reject('mask_31', lambda c, p: c['request']['target'].update(goal=FALSE))

    def test_selected_word_type_tamper(self):
        self.reject('mask_31', lambda c, p: c['request']['target']['source'].update(word_type='int'))

    def test_receipt_is_not_source_evidence(self):
        c, _, r, _ = self.proof()
        with self.assertRaises(ValueError):
            check(c['source'], c['request'], r)

    def test_missing_native_axiom_proof(self):
        self.reject('mask_31', lambda c, p: p['evidence']['facts'].pop())

    def test_unknown_native_rule(self):
        self.reject('mask_31', lambda c, p: p['evidence']['facts'][0].update(rule='trust-receipt'))

    def test_guard_removed_even_after_rebinding(self):
        def change(c, p):
            c['request']['guards'] = []
            p['binding'] = prepare(c['source'], c['request']).binding()
        self.reject('mask_guard_zero', change)

    def test_false_local_implication_even_after_rebinding(self):
        def change(c, p):
            c['source'] = c['source'].replace('2147483648L', '2147483649L')
            p['binding'] = prepare(c['source'], c['request']).binding()
        self.reject('mask_31', change)

    def test_mask_consequent_substitution(self):
        def change(c, p):
            f = next(f for f in p['evidence']['facts'] if f['rule'] == 'eq-mask')
            f['consequent'] = f['antecedent']
        self.reject('mask_31', change)

    def test_mask_bool_atom_index(self):
        def change(c, p):
            next(f for f in p['evidence']['facts'] if f['rule'] == 'eq-mask')['antecedent'] = False
        self.reject('mask_31', change)

    def test_low_bit_bad_row(self):
        def change(c, p):
            f = next(f for f in p['evidence']['facts'] if f['rule'] == 'low-bit')
            f['rows'][-1]['bits'] = [1, 1]
        self.reject('double_even', change)

    def test_low_bit_missing_dependency(self):
        def change(c, p):
            next(f for f in p['evidence']['facts'] if f['rule'] == 'low-bit')['rows'].pop(0)
        self.reject('double_even', change)

    def test_low_bit_reordered_dependencies(self):
        def change(c, p):
            next(f for f in p['evidence']['facts'] if f['rule'] == 'low-bit')['rows'].reverse()
        self.reject('double_even', change)

    def test_low_bit_bool_bit(self):
        def change(c, p):
            next(f for f in p['evidence']['facts'] if f['rule'] == 'low-bit')['rows'][0]['bits'][0] = False
        self.reject('double_even', change)

    def test_guard_abstraction_cannot_answer_uncovered_threshold(self):
        c = CASES['mask_31']
        ctx = prepare(c['source'], c['request'])
        self.assertEqual(ctx.limit, 1)
        g = Graph(ctx)
        high = g.node('t.popcount_eq.3')
        self.assertIsNone(guard_truth(ctx, g, high))
        with self.assertRaises(ValueError):
            check_fact(ctx, g, {'rule': 'guard-truth', 'term': high})

    def test_source_atom_is_not_a_guard_atom(self):
        c = CASES['mask_31']
        ctx = prepare(c['source'], c['request'])
        g = Graph(ctx)
        self.assertIsNone(guard_truth(ctx, g, g.atom(0)))

    def test_native_local_law_substitution(self):
        def change(c, p):
            next(f for f in p['evidence']['facts'] if f['rule'] == 'local')['law'] = 'word-cancel'
        self.reject('mask_31', change)

    def test_ground_goal_substitution(self):
        def change(c, p):
            q = p['evidence']['request']['queries'][0]
            q[1] = q[0]
        self.reject('mask_31', change)

    def test_ground_receipt_substitution(self):
        self.reject('mask_31', lambda c, p: p['evidence'].update(certificate={'status': 'equal'}))

    def test_circular_ground_premise(self):
        def change(c, p):
            events = p['evidence']['certificate']['events']
            i = next(i for i, e in enumerate(events) if e['rule'] == 'congruence')
            events[i]['premises'][0] = [i]
        self.reject('arithmetic_compound', change)

    def test_abstract_separator_is_not_a_program_refutation(self):
        _, p, r, _ = self.proof('power_open')
        self.assertEqual(p['kind'], 'ground')
        self.assertEqual(r['status'], 'unresolved')
        self.assertFalse(r['source_refutation'])
        self.assertTrue(r['abstract_nonconsequence'])

    def test_conditional_witness_satisfies_guard(self):
        c, _, r, _ = self.proof('arithmetic_guarded_mutant')
        ctx = prepare(c['source'], c['request'])
        w = r['witness']
        self.assertTrue(ctx.guard(w['input'].bit_count(), w['input'] >> (w['width'] - 1)))

    def test_witness_outside_guard(self):
        self.reject('arithmetic_guarded_mutant', lambda c, p: p['evidence'].update(width=1, input=0))

    def test_witness_bool_width(self):
        self.reject('mask_mutant', lambda c, p: p['evidence'].update(width=True))

    def test_witness_bool_input(self):
        self.reject('mask_mutant', lambda c, p: p['evidence'].update(input=True))

    def test_witness_must_recompute_source(self):
        self.reject('mask_mutant', lambda c, p: p['evidence'].update(input=0))

    def test_fixed_witness_width_is_exact(self):
        c = deepcopy(CASES['mask_mutant'])
        c['request']['width'] = {'kind': 'fixed', 'bits': 4}
        p, _, _ = prove(c['source'], c['request'])
        p['evidence']['width'] = 3
        with self.assertRaises(ValueError): check(c['source'], c['request'], p)

    def test_empty_domain_is_explicit(self):
        _, p, r, _ = self.proof('empty_guard')
        self.assertEqual(p['kind'], 'empty')
        self.assertTrue(r['vacuous'])
        self.assertEqual(r['status'], 'verified_empty_domain')

    def test_empty_domain_rebound_nonempty_rejected(self):
        def change(c, p):
            c['request']['guards'] = [['negative']]
            p['binding'] = prepare(c['source'], c['request']).binding()
        self.reject('empty_guard', change)

    def test_empty_fixed_domain_not_parametric(self):
        def change(c, p):
            c['request']['width'] = {'kind': 'all_positive'}
            p['binding'] = prepare(c['source'], c['request']).binding()
        self.reject('empty_fixed_guard', change)

    def test_dead_unsupported_code_is_not_skipped(self):
        _, p, r, _ = self.proof('unsupported_dead_statement')
        self.assertIsNone(p)
        self.assertEqual(r['status'], 'unsupported')

    def test_fallback_is_explicit_and_charged(self):
        _, p, r, w = self.proof('power_guarded_fallback')
        self.assertEqual(p['kind'], 'covered')
        self.assertTrue(r['fallback']['guard_checked'])
        self.assertGreater(w['counts']['legacy_builder_calls'], 0)
        self.assertGreater(w['counts']['native_rule_failures'], 0)
        self.assertEqual(w['counts']['fallback_attempts'], 1)
        self.assertIn('prior_ground_evidence', w)

    def test_fallback_changed_guard_after_rebinding(self):
        def change(c, p):
            c['request']['guards'] = [['nonnegative']]
            p['binding'] = prepare(c['source'], c['request']).binding()
        self.reject('power_guarded_fallback', change)

    def test_fallback_missing_reachable_state(self):
        self.reject('power_guarded_fallback', lambda c, p: p['evidence']['obligation']['states'].pop())

    def test_fallback_wrong_fixed_width_after_rebinding(self):
        def change(c, p):
            c['request']['width']['bits'] = 3
            p['binding'] = prepare(c['source'], c['request']).binding()
        self.reject('fixed_fallback', change)

    def test_fallback_source_budget_retains_failed_native_work(self):
        c = CASES['power_guarded_fallback']
        p, r, w = prove(c['source'], c['request'], fallback=True, limits={'max_source_states': 1})
        self.assertIsNone(p)
        self.assertEqual(r['status'], 'budget_exhausted')
        self.assertIn('prior_ground_evidence', w)
        self.assertGreater(w['counts']['fact_requests'], 0)

    def test_work_budget_never_returns_partial_positive(self):
        c = CASES['mask_31']
        p, r, w = prove(c['source'], c['request'], limits={'max_work': 0})
        self.assertIsNone(p)
        self.assertEqual(r['status'], 'budget_exhausted')
        self.assertGreater(w['counts']['research_calls'], 0)

    def test_zero_fact_budget_records_attempt(self):
        _, p, r, w = self.proof('fact_budget')
        self.assertIsNone(p)
        self.assertEqual(r['status'], 'budget_exhausted')
        self.assertEqual(w['fact_attempts'][0]['outcome'], 'budget_exhausted')

    def test_no_witness_budget_does_not_refute(self):
        c = CASES['mask_mutant']
        p, r, w = prove(c['source'], c['request'], limits={'max_witness_evaluations': 0})
        self.assertEqual(p['kind'], 'ground')
        self.assertEqual(r['status'], 'unresolved')
        self.assertEqual(w['counts'].get('witness_candidates', 0), 0)

    def test_bool_budget_rejected(self):
        c = CASES['mask_31']
        with self.assertRaises(ValueError): prove(c['source'], c['request'], limits={'max_work': True})

    def test_extended_guard_language_rejected(self):
        c = deepcopy(CASES['mask_31'])
        c['request']['guards'] = [['eq', 'x', 32]]
        with self.assertRaises(ValueError): prove(c['source'], c['request'])

    def test_fixed_zero_width_rejected(self):
        c = deepcopy(CASES['mask_31'])
        c['request']['width'] = {'kind': 'fixed', 'bits': 0}
        with self.assertRaises(ValueError): prove(c['source'], c['request'])

    def test_cyclic_request_rejected(self):
        c = deepcopy(CASES['mask_31'])
        c['request']['guards'].append(c['request'])
        with self.assertRaises(ValueError): prove(c['source'], c['request'])

    def test_certified_fixtures_match_separate_integer_execution(self):
        for c in CASES.values():
            if c['expected'] not in ('certified', 'verified_empty_domain'):
                continue
            ctx = prepare(c['source'], c['request'])
            for width in ([ctx.width] if ctx.width is not None else range(1, 7)):
                for raw in range(1 << width):
                    sign = raw >> (width - 1)
                    if ctx.guard(raw.bit_count(), sign):
                        self.assertEqual(evaluate(ctx.ir, raw, width),
                                         target_value(ctx.spec['target'], raw.bit_count(), sign),
                                         (c['name'], width, raw))

    def test_low_bit_rules_with_borrow_complement_and_wrap(self):
        for expr, bit in [('x+~x', 1), ('x-~x', 1), ('x & ~x', 0),
                          ('-x+x', 0), ('(x+7)-(x+2)', 1), ('(x|1)+(x|1)', 0)]:
            source = f'class Demo {{ static boolean f(long x) {{ return (({expr}) & 1) == {bit}; }} }}'
            request = make_request(target(TRUE))
            p, r, _ = prove(source, request)
            self.assertEqual(r['status'], 'certified', expr)
            ctx = prepare(source, request)
            for width in range(1, 7):
                for raw in range(1 << width): self.assertTrue(evaluate(ctx.ir, raw, width))
            self.assertEqual(check(source, request, p), r)

    def test_replay_rejects_preloaded_search(self):
        from .replay import run
        with self.assertRaisesRegex(ValueError, 'preloaded search'):
            run(Path('must-not-be-read'))

    def test_fresh_native_only_checker_normal_and_optimized(self):
        c, p, r, _ = self.proof('arithmetic_compound')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path/'source.java').write_text(c['source'])
            save_json(path/'request.json', c['request'])
            save_json(path/'proof.json', p)
            script = '''
import sys,json
from pathlib import Path
from research.source_query.replay import NoSearch
g=NoSearch(native_only=True)
if g.loaded():raise RuntimeError('preloaded search')
sys.meta_path.insert(0,g)
from research.source_query.context import load_json
from research.source_query.checker import check
p=Path(sys.argv[1])
print(json.dumps(check((p/'source.java').read_text(),load_json(p/'request.json'),load_json(p/'proof.json'))))
if g.loaded():raise RuntimeError('search loaded')
'''
            for flags in ([], ['-O']):
                result = subprocess.run([sys.executable, *flags, '-c', script, str(path)],
                                        text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), r)

    def test_cli_exclusive_certificate_output(self):
        c = CASES['mask_31']
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path/'source.java').write_text(c['source'])
            save_json(path/'request.json', c['request'])
            (path/'proof.json').write_text('keep this')
            run = subprocess.run([sys.executable, '-m', 'research.source_query.cli', 'prove',
                                  str(path/'source.java'), str(path/'request.json'), str(path/'proof.json')],
                                 capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 2)
            self.assertEqual((path/'proof.json').read_text(), 'keep this')


if __name__ == '__main__':
    unittest.main()
