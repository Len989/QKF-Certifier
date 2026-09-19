"""Signed inference, adversarial replay, old-route compatibility and CLI tests."""
import builtins
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from research.inference.adapters import conflict
from research.inference.v3_adapters import System
from research.inference.v3_checker import check
from research.inference.v3_producer import infer
from research.inference.v3_target_checker import SignedTarget
from research.observations.model import digest
from research.signed_predicates.semantics import evaluate
from research.unified import v3 as unified
from research.unified.checker import InvalidProof
from research.unified.v3_schema import compile_target

ROOT = Path(__file__).resolve().parents[2]
POSITIVE_POWER = ["and", ["positive"], ["popcount_eq", 1]]


def target(word_type="int", goal=None):
    return {"schema": "qkf-target-v2", "kind": "signed_boolean_predicate",
            "source": {"entry": {"class": "Demo", "method": "f"}, "word_type": word_type},
            "goal": deepcopy(POSITIVE_POWER if goal is None else goal)}


def source(expression="x > 0 && (x & (x - 1)) == 0", word_type="int"):
    return "class Demo { public static boolean f(" + word_type + " x) { return " + expression + "; } }"


class InferenceV3Tests(unittest.TestCase):
    def test_int_and_long_infer_compact_continuation_questions(self):
        for word_type in ("int", "long"):
            with self.subTest(word_type=word_type):
                s, t = source(word_type=word_type), target(word_type)
                cert, result = infer(s, t)
                self.assertEqual(result["status"], "certified")
                self.assertTrue(result["all_positive_widths"])
                self.assertEqual((result["native_states"], result["classes"],
                                  result["target_product_states"]), (6, 4, 5))
                self.assertEqual(result["selected_observations"], 3)
                self.assertTrue(all(r["kind"] == "terminal_after" for r in result["selected"]))
                self.assertEqual(check(s, t, cert), result)

    def test_all_signed_relations_and_symmetric_zero(self):
        for word_type in ("int", "long"):
            for op, reverse, atom in ((">", "<", "positive"), (">=", "<=", "nonnegative"),
                                      ("<", ">", "negative"), ("<=", ">=", "nonpositive")):
                for expression in ("x " + op + " 0", "0 " + reverse + " x"):
                    with self.subTest(word_type=word_type, expression=expression):
                        cert, result = infer(source(expression, word_type), target(word_type, [atom]))
                        self.assertEqual(result["status"], "certified")

    def test_pure_boolean_operators_and_annotations(self):
        cases = (("x > 0 & (x & (x - 1)) == 0", POSITIVE_POWER),
                 ("(x > 0) ^ (x < 0)", ["not", ["popcount_eq", 0]]),
                 ("x > 0 | x < 0", ["not", ["popcount_eq", 0]]),
                 ("!(x <= 0)", ["positive"]))
        for expression, goal in cases:
            s = source(expression).replace("public static", '@SuppressWarnings("unused") public static')
            cert, result = infer(s, target(goal=goal))
            self.assertEqual(result["status"], "certified")

    def test_constant_predicates_need_no_observations(self):
        for expression, goal in (("true", ["or", ["negative"], ["nonnegative"]]),
                                  ("false", ["and", ["negative"], ["nonnegative"]])):
            cert, result = infer(source(expression), target(goal=goal))
            self.assertEqual(result["status"], "certified")
            self.assertEqual(result["selected_observations"], 0)

    def test_features_are_independent_of_target_formula(self):
        first = System(source(), target())
        other = System(source(), target(goal=["negative"]))
        self.assertEqual(first.features, other.features)
        self.assertEqual(first.binding["candidate_library_sha256"], other.binding["candidate_library_sha256"])
        self.assertNotEqual(first.binding["target_sha256"], other.binding["target_sha256"])

    def test_method_rename_does_not_choose_observations(self):
        s, t = source(), target()
        renamed = deepcopy(t)
        renamed["source"]["entry"] = {"class": "Other", "method": "whatever"}
        rs = s.replace("Demo", "Other").replace(" f(", " whatever(")
        self.assertEqual(System(s, t).features, System(rs, renamed).features)
        c1, r1 = infer(s, t)
        c2, r2 = infer(rs, renamed)
        self.assertEqual(c1["selected"], c2["selected"])
        self.assertEqual(r1, r2)
        with self.assertRaises(ValueError):
            check(rs, renamed, c1)

    def test_deterministic_certificate(self):
        first, result = infer(source(), target())
        second, other = infer(source(), target())
        self.assertEqual(digest(first), digest(second))
        self.assertEqual(result, other)

    def test_final_selection_is_single_deletion_irredundant(self):
        s, t = source(), target()
        cert, result = infer(s, t)
        system = System(s, t)
        self.assertIsNone(conflict(system, cert["selected"]))
        for fid in cert["selected"]:
            self.assertIsNotNone(conflict(system, [x for x in cert["selected"] if x != fid]))
        self.assertTrue(result["single_deletion_irredundant"])

    def test_sign_bit_only_negative_control_has_native_ir_witness(self):
        for word_type, width in (("int", 32), ("long", 64)):
            s = source("x != 0 && (x & (x - 1)) == 0", word_type)
            cert, result = infer(s, target(word_type))
            self.assertEqual(result["status"], "refuted")
            self.assertEqual(result["witness_width"], 1)
            self.assertFalse(result["all_positive_widths"])
            self.assertIn(1 << (width - 1), [r["input"] for r in result["native_width_witnesses"]])
            self.assertEqual(check(s, target(word_type), cert), result)

    def test_counterexample_must_fail_at_final_width(self):
        s, t = source("x != 0 && (x & (x - 1)) == 0"), target()
        cert, _ = infer(s, t)
        self.assertEqual(cert["target_proof"]["word"], ["1"])
        cert["target_proof"]["word"].append("0")
        with self.assertRaisesRegex(ValueError, "final width"):
            check(s, t, cert)

    def test_sign_and_zero_guard_mutants_are_refuted(self):
        for expression in ("(x & (x - 1)) == 0", "x >= 0 && (x & (x - 1)) == 0",
                           "x < 0 && (x & (x - 1)) == 0", "x > 0 || (x & (x - 1)) == 0"):
            cert, result = infer(source(expression), target())
            self.assertEqual(result["status"], "refuted")
            self.assertEqual(check(source(expression), target(), cert), result)

    def test_exhaustive_small_width_quotient_vs_whole_word(self):
        expressions = ("x > 0 && (x & (x - 1)) == 0", "(x + 1) < 0", "(-x) >= 0",
                       "(x > 0) ^ ((x & (x - 1)) == 0)", "(x & (x - 1)) != 0")
        for expression in expressions:
            s, t = source(expression), target()
            cert, _ = infer(s, t)
            system = System(s, t)
            monitor = SignedTarget(system, cert["selected"])
            for width in range(1, 9):
                for x in range(1 << width):
                    state = monitor.initial
                    for i in range(width):
                        state = monitor.transition(state, str((x >> i) & 1))
                    actual = system.terminal(monitor.blocks[state[0]][0]) == "true"
                    self.assertEqual(actual, evaluate(system.ir, x, width))

    def test_source_target_and_library_binding_mutations_rejected(self):
        s, t = source(), target()
        cert, _ = infer(s, t)
        for field in cert["binding"]:
            bad = deepcopy(cert)
            bad["binding"][field] = "forged"
            with self.subTest(field=field), self.assertRaises(ValueError):
                check(s, t, bad)
        with self.assertRaises(ValueError):
            check(s + "\n", t, cert)
        with self.assertRaises(ValueError):
            check(s, target(goal=["nonnegative"]), cert)

    def test_conflict_trace_and_selected_mutations_rejected(self):
        cert, _ = infer(source(), target())
        variants = []
        for key in ("selected", "refinements"):
            bad = deepcopy(cert); bad[key] = []; variants.append(bad)
        bad = deepcopy(cert); bad["refinements"][0]["conflict"]["reason"] = "forged"; variants.append(bad)
        bad = deepcopy(cert); bad["refinements"][0]["feature"] = "absent"; variants.append(bad)
        bad = deepcopy(cert); bad["pruning"][0]["removed"] = True; variants.append(bad)
        for bad in variants:
            with self.assertRaises(ValueError):
                check(source(), target(), bad)

    def test_partition_int_bool_confusion_rejected(self):
        cert, _ = infer(source(), target())
        cert["blocks"][0][0][0] = bool(cert["blocks"][0][0][0])
        with self.assertRaisesRegex(ValueError, "partition"):
            check(source(), target(), cert)

    def test_product_state_parent_and_closure_mutations_rejected(self):
        cert, _ = infer(source(), target())
        variants = []
        for value in (True, -1, 999999):
            bad = deepcopy(cert); bad["target_proof"]["states"][0]["state"][0] = value; variants.append(bad)
        bad = deepcopy(cert); bad["target_proof"]["states"].pop(); variants.append(bad)
        bad = deepcopy(cert); bad["target_proof"]["states"][1]["parent"] = [True, "0"]; variants.append(bad)
        bad = deepcopy(cert); bad["target_proof"]["states"][1]["parent"][1] = "2"; variants.append(bad)
        for bad in variants:
            with self.assertRaises(ValueError):
                check(source(), target(), bad)

    def test_unified_prove_check_and_forged_result(self):
        result, envelope = unified.prove(source(), target())
        self.assertEqual(unified.check(source(), target(), envelope), result)
        envelope["result"]["all_positive_widths"] = False
        with self.assertRaises(InvalidProof):
            unified.check(source(), target(), envelope)

    def test_budget_exhausted_never_returns_certificate(self):
        for budgets in ({"max_features": 0}, {"max_target_states": 1}):
            result, envelope = unified.prove(source(), target(), budgets=budgets)
            self.assertEqual(result["status"], "budget_exhausted")
            self.assertFalse(result["all_positive_widths"])
            self.assertIsNone(envelope)

    def test_invalid_budget_fields_and_bool_values_rejected(self):
        for budgets in ({"max_features": True}, {"max_target_states": 0}, {"typo": 3}):
            with self.assertRaises(ValueError):
                unified.prove(source(), target(), budgets=budgets)

    def test_unsupported_calls_shifts_order_and_branches(self):
        cases = (source("(x + 1) < (x - 1)"), source("(x >> 1) > 0"),
                 source("helper(x) > 0"), source().replace("return", "if (x == 0) return false; return", 1))
        for s in cases:
            result, envelope = unified.prove(s, target())
            self.assertEqual(result["status"], "unsupported")
            self.assertIsNone(envelope)

    def test_target_versions_remain_separate(self):
        from research.unified.schema import compile_target as old_compile
        with self.assertRaises(ValueError):
            old_compile(target())
        bad = target(); bad["goal"] = ["positive", 1]
        with self.assertRaises(ValueError):
            compile_target(bad)

    def test_old_word_predicate_and_successor_routes(self):
        from research.inference.test_inference_v2 import LOW_SOURCE, LOW_TARGET, PRED_SOURCE, PRED_TARGET, SUCCESSOR_TARGET
        for s, t in ((LOW_SOURCE, LOW_TARGET), (PRED_SOURCE, PRED_TARGET),
                     ((ROOT / "research/observations/evidence/ascending/original.java").read_text(), SUCCESSOR_TARGET)):
            result, envelope = unified.prove(s, t)
            self.assertEqual(result["status"], "certified")
            self.assertEqual(unified.check(s, t, envelope), result)

    def test_old_negative_successor_route(self):
        from research.inference.test_inference_v2 import SUCCESSOR_TARGET
        s = (ROOT / "research/observations/evidence/ascending/clear_repair.java").read_text()
        result, envelope = unified.prove(s, SUCCESSOR_TARGET)
        self.assertEqual(result["status"], "refuted")
        self.assertEqual(unified.check(s, SUCCESSOR_TARGET, envelope), result)

    def test_legacy_unified_envelope_replays_unchanged(self):
        from research.unified.producer import prove as old_prove
        from research.inference.test_inference_v2 import LOW_SOURCE, LOW_TARGET
        result, envelope = old_prove(LOW_SOURCE, LOW_TARGET)
        self.assertEqual(unified.check(LOW_SOURCE, LOW_TARGET, envelope), result)

    def test_masked_bounds_keep_the_retained_route(self):
        from research.unified.test_unified import TYPED, MAXIMUM_TARGET, envelope_from_typed
        for name in ("descending.original.maximum", "descending.strict.maximum"):
            s, envelope, result = envelope_from_typed(TYPED / name, MAXIMUM_TARGET)
            self.assertEqual(unified.check(s, MAXIMUM_TARGET, envelope), result)
            with mock.patch("research.unified.producer.prove", return_value=(result, envelope)) as legacy:
                self.assertEqual(unified.prove(s, MAXIMUM_TARGET), (result, envelope))
                legacy.assert_called_once_with(s, MAXIMUM_TARGET, budgets=None)

    def test_frozen_v2_engine_identity_unchanged(self):
        from research.external.frozen_v2.experiment import check_engine
        check_engine()

    def test_replay_without_producer_native_or_smt_imports(self):
        result, envelope = unified.prove(source(), target())
        original = builtins.__import__
        def guard(name, *args, **kwargs):
            if "producer" in name or name in {"subprocess", "z3", "cvc5", "pysmt"}:
                raise AssertionError("forbidden replay dependency: " + name)
            return original(name, *args, **kwargs)
        with mock.patch("builtins.__import__", side_effect=guard):
            self.assertEqual(unified.check(source(), target(), envelope), result)

    def test_fresh_process_replay_blocks_imports_before_checker_load(self):
        result, envelope = unified.prove(source(), target())
        script = '''import builtins, json, sys
original = builtins.__import__
def guard(name, *args, **kwargs):
    if 'producer' in name or name in {'subprocess','z3','cvc5','pysmt'}:
        raise AssertionError('forbidden fresh replay dependency: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guard
from research.unified.v3 import check
s, t, e = json.load(sys.stdin)
print(json.dumps(check(s, t, e), sort_keys=True))
'''
        completed = subprocess.run([sys.executable, "-O", "-c", script], cwd=ROOT,
                                   input=json.dumps([source(), target(), envelope]),
                                   text=True, capture_output=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), result)

    def test_cli_exit_codes_and_no_proof_on_budget_exhaustion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); sp = root / "Demo.java"; tp = root / "target.json"; pp = root / "proof.json"
            sp.write_text(source()); tp.write_text(json.dumps(target()))
            argv = [str(sp), "--target", str(tp), "--proof", str(pp)]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(unified.main(["prove", *argv]), 0)
                self.assertEqual(unified.main(["check", *argv]), 0)
                bad = json.loads(pp.read_text()); bad["proof"]["selected"] = []; pp.write_text(json.dumps(bad))
                self.assertEqual(unified.main(["check", *argv]), 3)
                pp.unlink(); budget = root / "budget.json"; budget.write_text('{"max_features": 0}')
                self.assertEqual(unified.main(["prove", *argv, "--budget", str(budget)]), 2)
                self.assertFalse(pp.exists())
                sp.write_text(source("x != 0 && (x & (x - 1)) == 0"))
                self.assertEqual(unified.main(["prove", *argv]), 1)
                self.assertEqual(unified.main(["check", *argv]), 1)
                tp.write_text('{"schema":"a", "schema":"b"}')
                self.assertEqual(unified.main(["check", *argv]), 64)


if __name__ == "__main__":
    unittest.main()
