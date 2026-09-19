import builtins
from copy import deepcopy
import unittest
from unittest import mock

from research.inference.checker import check
from research.inference.producer import InferenceFailure, infer

LOW_SOURCE = "class Demo { public static long low(long x) { return x & -x; } }\n"
LOW_TARGET = {
    "schema": "qkf-target-v1",
    "kind": "word_result",
    "source": {"entry": {"class": "Demo", "method": "low"}, "word_type": "long"},
    "goal": ["lowest_set_bit"],
}
PRED_SOURCE = "class Demo { public static boolean p(int x) { return (x & (x - 1)) == 0; } }\n"
PRED_TARGET = {
    "schema": "qkf-target-v1",
    "kind": "boolean_predicate",
    "source": {"entry": {"class": "Demo", "method": "p"}, "word_type": "int"},
    "goal": ["popcount_le", 1],
}


class InferenceTests(unittest.TestCase):
    def test_lowbit_inference_closes_independent_target(self):
        cert, result = infer(LOW_SOURCE, LOW_TARGET)
        self.assertEqual(result["status"], "certified")
        self.assertEqual(result["target_status"], "certified")
        self.assertGreater(result["candidate_observations"], 0)
        self.assertLessEqual(result["selected_observations"], result["candidate_observations"])
        self.assertEqual(check(LOW_SOURCE, LOW_TARGET, cert), result)

    def test_predicate_inference_closes_terminal_target(self):
        cert, result = infer(PRED_SOURCE, PRED_TARGET)
        self.assertEqual(result["status"], "certified")
        self.assertEqual(result["target_status"], "certified")
        self.assertEqual(result["family"], "terminal-predicate")
        self.assertEqual(check(PRED_SOURCE, PRED_TARGET, cert), result)

    def test_irrelevant_arithmetic_residual_is_not_selected(self):
        source = "class Demo { public static long f(long x) { long t = -x; return x; } }\n"
        target = {
            "schema": "qkf-target-v1",
            "kind": "word_result",
            "source": {"entry": {"class": "Demo", "method": "f"}, "word_type": "long"},
            "goal": ["equals", ["input"]],
        }
        cert, result = infer(source, target)
        self.assertEqual(result["status"], "certified")
        self.assertEqual(result["selected_observations"], 0)
        self.assertEqual(result["classes"], 1)
        self.assertEqual(cert["selected"], [])

    def test_wrong_program_is_refuted_after_interface_inference(self):
        source = "class Demo { public static long f(long x) { return x; } }\n"
        target = deepcopy(LOW_TARGET)
        target["source"]["entry"] = {"class": "Demo", "method": "f"}
        cert, result = infer(source, target)
        self.assertEqual(result["status"], "refuted")
        self.assertEqual(result["target_status"], "refuted")
        self.assertEqual(check(source, target, cert), result)

    def test_feature_budget_is_distinct_from_refutation(self):
        with self.assertRaises(InferenceFailure):
            infer(LOW_SOURCE, LOW_TARGET, max_features=0)

    def test_changed_selected_set_is_rejected(self):
        cert, _ = infer(LOW_SOURCE, LOW_TARGET)
        broken = deepcopy(cert)
        broken["selected"] = []
        with self.assertRaises(ValueError):
            check(LOW_SOURCE, LOW_TARGET, broken)

    def test_changed_refinement_witness_is_rejected(self):
        cert, _ = infer(LOW_SOURCE, LOW_TARGET)
        self.assertTrue(cert["refinements"])
        broken = deepcopy(cert)
        broken["refinements"][0]["conflict"]["reason"] = "terminal"
        with self.assertRaises(ValueError):
            check(LOW_SOURCE, LOW_TARGET, broken)

    def test_replay_does_not_import_producer(self):
        cert, result = infer(PRED_SOURCE, PRED_TARGET)
        real_import = builtins.__import__

        def guarded(name, *args, **kwargs):
            if "producer" in name or name in {"subprocess", "z3", "cvc5", "pysmt"}:
                raise AssertionError("forbidden inference replay import: " + name)
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=guarded):
            self.assertEqual(check(PRED_SOURCE, PRED_TARGET, cert), result)


if __name__ == "__main__":
    unittest.main()
