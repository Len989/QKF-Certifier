"""Constructed target/replay tests; no external holdout discovery or network."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from research.signed_runtime.runtime import load
from research.signed_bridge.model import read
from research.signed_predicates.semantics import evaluate
from research.signed_predicates.frontend import target_value
from research.inference.test_inference_v3 import source, target
from research.unified import v4
from research.unified.checker import InvalidProof
from .common import Monitor, prepare
from .checker import check_product

ROOT = Path(__file__).resolve().parents[2]


class RowTargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s, cls.t = source(), target()
        cls.result, cls.envelope = v4.prove(cls.s, cls.t)

    def test_signed_positive_int_long(self):
        for typ in ('int', 'long'):
            r, p = v4.prove(source(word_type=typ), target(typ))
            self.assertEqual(r['status'], 'certified')
            self.assertTrue(r['target_checked'] and r['all_positive_widths'])
            self.assertFalse(r['lean_checked'])
            self.assertEqual(r['inner']['target']['product_states'], 6)
            self.assertEqual(r['inner']['runtime']['classes'], 5)
            self.assertEqual(v4.check(source(word_type=typ), target(typ), p), r)

    def test_signed_atom_relations_and_reversed_operands(self):
        for typ in ('int', 'long'):
            for op, rev, atom in [('>', '<', 'positive'), ('>=', '<=', 'nonnegative'),
                                   ('<', '>', 'negative'), ('<=', '>=', 'nonpositive')]:
                for expr in ('x '+op+' 0', '0 '+rev+' x'):
                    self.assertEqual(v4.prove(source(expr, typ), target(typ, [atom]))[0]['status'], 'certified')

    def test_boolean_compositions(self):
        for expr, goal in [('x > 0 | x < 0', ['not', ['popcount_eq', 0]]),
                           ('(x > 0) ^ (x < 0)', ['xor', ['positive'], ['negative']]),
                           ('!(x <= 0)', ['positive'])]:
            self.assertEqual(v4.prove(source(expr), target(goal=goal))[0]['status'], 'certified')

    def test_constant_and_empty_completion(self):
        for expr, op in [('true', 'or'), ('false', 'and')]:
            r, p = v4.prove(source(expr), target(goal=[op, ['negative'], ['nonnegative']]))
            self.assertEqual(r['status'], 'certified')
            self.assertEqual(r['inner']['runtime']['classes'], 2)
            compiled, selection = prepare(target(goal=[op, ['negative'], ['nonnegative']]))
            runner, _ = load(source(expr), selection, p['proof']['observations'])
            monitor = Monitor(runner, compiled['specification'])
            with self.assertRaisesRegex(ValueError, 'positive-width'):
                monitor.actual(monitor.initial)

    def test_target_count_saturation_against_word_semantics(self):
        rng = random.Random(31001)
        for goal in [['popcount_eq', k] for k in range(4)] + [['popcount_le', k] for k in range(4)]:
            compiled, selection = prepare(target(goal=goal))
            runner, _ = load(self.s, selection, self.envelope['proof']['observations'])
            m = Monitor(runner, compiled['specification'])
            for width in range(1, 18):
                for _ in range(15):
                    x = rng.getrandbits(width); state = m.initial
                    for i in range(width):
                        state = m.step(state, str((x >> i) & 1))
                    self.assertEqual(m.expected(state), target_value(goal, x.bit_count(), x >> (width-1)))

    def test_monitor_all_small_words_vs_ir_and_raw_target(self):
        for expr in ['x > 0 && (x & (x - 1)) == 0', 'x + 1 < 0', '(-x) >= 0', 'x == 16']:
            s = source(expr); r, p = v4.prove(s, self.t)
            compiled, selection = prepare(self.t)
            runner, _ = load(s, selection, p['proof']['observations'])
            m, ir = Monitor(runner, compiled['specification']), read(s, selection)
            for width in range(1, 8):
                for x in range(1 << width):
                    state = m.initial
                    for i in range(width):
                        state = m.step(state, str((x >> i) & 1))
                    self.assertEqual(m.actual(state), evaluate(ir, x, width))
                    self.assertEqual(m.expected(state), x > 0 and x < (1 << (width-1)) and x.bit_count() == 1)

    def test_sign_only_mutant_native_witness(self):
        for typ, width in [('int', 32), ('long', 64)]:
            r, _ = v4.prove(source('x != 0 && (x & (x - 1)) == 0', typ), target(typ))
            self.assertEqual(r['status'], 'refuted')
            self.assertIn(1 << (width-1), [x['input'] for x in r['inner']['target']['native_width_witnesses']])

    def test_missing_zero_and_wrong_connective(self):
        for expr in ['(x & (x - 1)) == 0', 'x >= 0 && (x & (x - 1)) == 0',
                     'x > 0 || (x & (x - 1)) == 0']:
            r, p = v4.prove(source(expr), self.t)
            self.assertEqual(r['status'], 'refuted')
            self.assertTrue(r['inner']['source_interface_verified'])
            self.assertFalse(r['all_positive_widths'])
            self.assertEqual(v4.check(source(expr), self.t, p), r)

    def test_small_width_refutation_does_not_invent_native_witness(self):
        s, t = source('x > 0 || (x == 2 && x < 0)'), target(goal=['positive'])
        r, _ = v4.prove(s, t)
        self.assertEqual(r['status'], 'refuted')
        self.assertEqual(r['inner']['target']['witness_width'], 2)
        self.assertEqual(r['inner']['target']['native_width_witnesses'], [])

    def test_counterexample_requires_failure_at_final_width(self):
        s = source('x != 0 && (x & (x - 1)) == 0')
        _, p = v4.prove(s, self.t)
        p['proof']['obligation']['word'].append('0')
        with self.assertRaisesRegex(InvalidProof, 'final width'):
            v4.check(s, self.t, p)

    def test_invalid_witness_words(self):
        s = source('true'); _, p = v4.prove(s, self.t)
        for word in [[], ['2'], [True], [1], '0', ['0']*4097]:
            bad = deepcopy(p); bad['proof']['obligation']['word'] = word
            with self.assertRaises(InvalidProof):
                v4.check(s, self.t, bad)

    def test_source_and_target_bindings(self):
        for s, t in [(self.s+'\n', self.t), (self.s, target(goal=['positive'])),
                     (self.s, target('long'))]:
            with self.assertRaises(InvalidProof):
                v4.check(s, t, self.envelope)

    def test_every_binding_field_is_checked(self):
        for field in self.envelope['proof']['binding']:
            bad = deepcopy(self.envelope); bad['proof']['binding'][field] = 'forged'
            with self.assertRaises(InvalidProof):
                v4.check(self.s, self.t, bad)

    def test_rehashed_target_change_still_checks_goal(self):
        t = target(goal=['negative']); bad = deepcopy(self.envelope)
        compiled, _ = prepare(t)
        for key in ['target_sha256', 'specification_sha256']:
            bad['proof']['binding'][key] = compiled[key]
        with self.assertRaises(InvalidProof):
            v4.check(self.s, t, bad)

    def test_saved_verdict_and_scope_are_not_trusted(self):
        for key, val in [('status', 'refuted'), ('all_positive_widths', False), ('lean_checked', True)]:
            bad = deepcopy(self.envelope); bad['result'][key] = val
            with self.assertRaises(InvalidProof):
                v4.check(self.s, self.t, bad)

    def test_source_only_proofs_cannot_prove_target(self):
        observations = self.envelope['proof']['observations']
        for p in [observations, observations['source_model'], observations['observations'], {}]:
            with self.assertRaises(InvalidProof):
                v4.check(self.s, self.t, p)

    def test_schema_engine_and_extra_fields(self):
        for field, value in [('schema', 'absent'), ('kind', 'word_result'), ('engine', 'observation-inference-v3'), ('extra', True)]:
            bad = deepcopy(self.envelope); bad[field] = value
            with self.assertRaises(InvalidProof):
                v4.check(self.s, self.t, bad)

    def test_product_type_confusions(self):
        for coordinate in range(3):
            for value in [True, -1, 999999, 0.0, '0']:
                bad = deepcopy(self.envelope)
                bad['proof']['obligation']['states'][0]['state'][coordinate] = value
                with self.assertRaises(InvalidProof):
                    v4.check(self.s, self.t, bad)

    def test_product_initial_parent_and_symbol(self):
        for parent in [[0, '0'], [True, '0'], [-1, '0'], [999, '0'], [0, '2']]:
            bad = deepcopy(self.envelope)
            bad['proof']['obligation']['states'][1]['parent'] = parent
            # [0,'0'] can be a real parent: change the child to the root too.
            bad['proof']['obligation']['states'][1]['state'] = bad['proof']['obligation']['states'][0]['state']
            with self.assertRaises(InvalidProof):
                v4.check(self.s, self.t, bad)

    def test_product_cyclic_parent_and_false_reachability(self):
        for parent in [[1, '0'], [2, '0'], [0, '1']]:
            bad = deepcopy(self.envelope); bad['proof']['obligation']['states'][1]['parent'] = parent
            with self.assertRaises(InvalidProof):
                v4.check(self.s, self.t, bad)

    def test_product_omission_duplicate_empty_extra(self):
        for variant in ['omit', 'duplicate', 'empty', 'extra']:
            bad = deepcopy(self.envelope); states = bad['proof']['obligation']['states']
            if variant == 'omit': states.pop()
            if variant == 'duplicate': states.append(deepcopy(states[-1]))
            if variant == 'empty': states.clear()
            if variant == 'extra': states[0]['guess'] = True
            with self.assertRaises(InvalidProof):
                v4.check(self.s, self.t, bad)

    def test_rows_cells_and_terminal_corruption(self):
        for part in ['rows', 'cells', 'separators', 'predicates', 'blocks']:
            bad = deepcopy(self.envelope); bad['proof']['observations']['observations'][part] = []
            with self.assertRaises(InvalidProof):
                v4.check(self.s, self.t, bad)

    def test_good_source_interface_for_wrong_program_is_not_target_proof(self):
        s = source('true'); r, p = v4.prove(s, self.t)
        self.assertTrue(r['inner']['runtime']['status'] == 'source_runtime_verified')
        self.assertEqual(r['status'], 'refuted')
        self.assertNotEqual(p['proof']['observations']['binding'], self.envelope['proof']['observations']['binding'])

    def test_observations_independent_of_goal(self):
        _, p = v4.prove(self.s, target(goal=['negative']))
        self.assertEqual(p['proof']['observations'], self.envelope['proof']['observations'])

    def test_determinism_and_caller_mutation(self):
        t = deepcopy(self.t); r, p = v4.prove(self.s, t)
        t['goal'] = ['negative']
        self.assertEqual(p, self.envelope)
        self.assertEqual(r, self.result)

    def test_source_model_observation_and_product_budgets(self):
        for b, stage in [({'max_states': 1}, 'source_model'), ({'max_observations': 0}, 'observation_closure'),
                          ({'max_classes': 1}, 'observation_closure'), ({'max_pullbacks': 0}, 'observation_closure'),
                          ({'max_target_states': 1}, 'target_product')]:
            r, p = v4.prove(self.s, self.t, budgets=b)
            self.assertIsNone(p); self.assertEqual(r['status'], 'budget_exhausted')
            self.assertEqual(r['inner']['stage'], stage)
            self.assertFalse(r['target_checked'] or r['all_positive_widths'])

    def test_witness_budget_has_no_refutation_certificate(self):
        r, p = v4.prove(source('true'), self.t, budgets={'max_witness_bits': 0})
        self.assertEqual(r['status'], 'budget_exhausted'); self.assertIsNone(p)

    def test_invalid_resource_ceiling_and_unknown_fields(self):
        for b in [{'max_states': True}, {'max_target_states': 0}, {'max_witness_bits': -1},
                  {'max_features': 2}, {'max_observations': 64}, {'max_pullbacks': 100001}]:
            with self.assertRaises(ValueError): v4.prove(self.s, self.t, budgets=b)

    def test_unsupported_source_has_no_proof(self):
        for expr in ['x >> 1 > 0', 'helper(x) > 0', 'x + 1 < x']:
            r, p = v4.prove(source(expr), self.t)
            self.assertEqual(r['status'], 'unsupported'); self.assertIsNone(p)

    def test_wrong_goal_schema_not_silently_adapted(self):
        for g in [['equals', 16], ['positive', 1], ['popcount_eq', 4], ['popcount_eq', True]]:
            with self.assertRaises(ValueError): v4.prove(self.s, target(goal=g))

    def test_positive_product_uses_only_rows_after_load(self):
        compiled, selection = prepare(self.t)
        runner, _ = load(self.s, selection, self.envelope['proof']['observations'])
        monitor = Monitor(runner, compiled['specification'])
        def profile(frame, event, arg):
            if event == 'call':
                name = frame.f_globals.get('__name__', '')
                if name.startswith('research.') and not name.startswith(('research.signed_targets', 'research.signed_runtime', 'research.signed_predicates.frontend', 'research.observations.model')):
                    raise AssertionError('source or search call during product: ' + name)
        sys.setprofile(profile)
        try:
            self.assertEqual(check_product(monitor, self.envelope['proof']['obligation'])['status'], 'certified')
        finally:
            sys.setprofile(None)

    def test_no_source_word_evaluation_on_positive_replay(self):
        with patch('research.signed_predicates.semantics.evaluate', side_effect=AssertionError('positive path evaluated whole word')):
            self.assertEqual(v4.check(self.s, self.t, self.envelope), self.result)

    def test_explanation_checks_target_and_interface(self):
        e = v4.explain(self.s, self.t, self.envelope)
        self.assertEqual(e['result'], self.result)
        self.assertEqual(e['obligation']['status'], 'certified')
        bad = deepcopy(self.envelope); bad['result']['status'] = 'refuted'
        with self.assertRaises(InvalidProof): v4.explain(self.s, self.t, bad)

    def test_legacy_v1_and_v3_proofs_keep_original_checkers(self):
        from research.unified.producer import prove as old_prove
        from research.unified.v3 import prove as v3_prove
        from research.unified.experiment import WORD_SOURCE, WORD_TARGET, PRED_SOURCE, PRED_TARGET
        for fn, s, t in [(old_prove, WORD_SOURCE, WORD_TARGET), (v3_prove, PRED_SOURCE, PRED_TARGET),
                          (v3_prove, self.s, self.t)]:
            r, p = fn(s, t)
            self.assertEqual(v4.check(s, t, p), r)
            self.assertNotEqual(p['schema'], v4.PROOF_SCHEMA)

    def test_nonsigned_new_discovery_keeps_delegated_route(self):
        from research.unified.v3 import prove as old
        from research.unified.experiment import WORD_SOURCE, WORD_TARGET, PRED_SOURCE, PRED_TARGET
        for s, t in [(WORD_SOURCE, WORD_TARGET), (PRED_SOURCE, PRED_TARGET)]:
            self.assertEqual(v4.prove(s, t), old(s, t))

    def test_guarded_fresh_process_normal_and_optimized(self):
        s = source('x != 0 && (x & (x - 1)) == 0'); r, p = v4.prove(s, self.t)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'proofs.json'
            path.write_text(json.dumps([[self.s, self.t, self.envelope, self.result], [s, self.t, p, r]]))
            script = '''import builtins,json,sys
original=builtins.__import__
def guarded(name,*args,**kwargs):
 if 'producer' in name or name.split('.')[0] in {'subprocess','z3','cvc5','pysmt'}:
  raise RuntimeError('forbidden import: '+name)
 return original(name,*args,**kwargs)
builtins.__import__=guarded
from research.unified.v4 import check,explain
for s,t,p,r in json.load(open(sys.argv[1])):
 if check(s,t,p)!=r or explain(s,t,p)['result']!=r: raise RuntimeError('replay failed')
'''
            for flags in [[], ['-O']]:
                run = subprocess.run([sys.executable, *flags, '-c', script, str(path)], cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)

    def test_cli_positive_refuted_and_explain_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); src, tgt, proof = root/'s.java', root/'t.json', root/'p.json'
            tgt.write_text(json.dumps(self.t))
            for expr, expected in [('x > 0 && (x & (x - 1)) == 0', 0), ('true', 1)]:
                src.write_text(source(expr)); proof.unlink(missing_ok=True)
                for command in ['prove', 'check', 'explain']:
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(v4.main([command, str(src), '--target', str(tgt), '--proof', str(proof)]), expected)

    def test_cli_no_overwrite_and_no_partial_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); src,tgt,p,b = [root/n for n in ['s.java','t.json','p.json','b.json']]
            src.write_text(self.s); tgt.write_text(json.dumps(self.t)); b.write_text('{"max_target_states":1}')
            args=['prove',str(src),'--target',str(tgt),'--proof',str(p)]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(v4.main(args+['--budget',str(b)]),2); self.assertFalse(p.exists())
                p.write_text('preserve'); self.assertEqual(v4.main(args),64)
            self.assertEqual(p.read_text(),'preserve')

    def test_cli_invalid_certificate_json_and_input_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); src,tgt,p = [root/n for n in ['s.java','t.json','p.json']]
            src.write_text(self.s); tgt.write_text(json.dumps(self.t))
            args=['check',str(src),'--target',str(tgt),'--proof',str(p)]
            for payload in ['{"a":1,"a":2}', '{"x":NaN}', '{}']:
                p.write_text(payload)
                with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(v4.main(args),3)
            tgt.write_text('{}')
            with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(v4.main(args),64)


if __name__ == '__main__':
    unittest.main()
