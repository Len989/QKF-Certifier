import builtins
from pathlib import Path
import unittest
from unittest import mock

from research.inference.v2_adapters import System
from research.inference.v2_checker import check
from research.inference.v2_producer import infer

ROOT = Path(__file__).resolve().parents[2]
ASCENDING = ROOT / "research/observations/evidence/ascending"

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
SUCCESSOR_TARGET = {
    "schema": "qkf-target-v1",
    "kind": "successor",
    "source": {"profile": "ascending"},
    "goal": {"claim": "cyclic_successor"},
}


class InferenceV2Tests(unittest.TestCase):
    def test_lowbit_and_predicate_still_close_directly(self):
        for source, target in ((LOW_SOURCE, LOW_TARGET), (PRED_SOURCE, PRED_TARGET)):
            cert, result = infer(source, target)
            self.assertEqual(result["status"], "certified")
            self.assertEqual(result["target_status"], "certified")
            self.assertEqual(check(source, target, cert), result)

    def test_original_graal_successor_now_closes_directly(self):
        source = (ASCENDING / "original.java").read_text(encoding="utf-8")
        cert, result = infer(source, SUCCESSOR_TARGET)
        self.assertEqual(result["status"], "certified")
        self.assertEqual(result["target_status"], "certified")
        self.assertGreater(result["target_product_states"], 0)
        self.assertGreater(result["target_checked_transitions"], 0)
        self.assertEqual(check(source, SUCCESSOR_TARGET, cert), result)

    def test_irrelevant_graal_registers_are_pruned_but_target_stays_closed(self):
        source = (ASCENDING / "irrelevant_register.java").read_text(encoding="utf-8")
        cert, result = infer(source, SUCCESSOR_TARGET)
        self.assertEqual(result["status"], "certified")
        self.assertEqual(result["target_status"], "certified")
        selected = " ".join(x["label"] for x in result["selected"])
        self.assertNotIn("register[1]", selected)
        self.assertNotIn("register[2]", selected)
        self.assertEqual(check(source, SUCCESSOR_TARGET, cert), result)

    def test_clear_repair_is_directly_refuted(self):
        source = (ASCENDING / "clear_repair.java").read_text(encoding="utf-8")
        cert, result = infer(source, SUCCESSOR_TARGET)
        self.assertEqual(result["status"], "refuted")
        self.assertEqual(result["target_status"], "refuted")
        self.assertIn(
            result["target_reason"],
            {"obligation_0", "obligation_1", "obligation_2", "obligation_3", "obligation_4"},
        )
        self.assertGreater(result["witness_width"], 0)
        self.assertEqual(check(source, SUCCESSOR_TARGET, cert), result)

    def test_order_cut_feature_is_available_and_selected(self):
        source = "class Demo { public static long f(long x) { return x + 3L; } }\n"
        target = {
            "schema": "qkf-target-v1",
            "kind": "word_result",
            "source": {"entry": {"class": "Demo", "method": "f"}, "word_type": "long"},
            "goal": ["equals", ["add", ["input"], ["const", 3]]],
        }
        system = System(source, target)
        self.assertTrue(any(f["kind"] == "le" for f in system.features))
        cert, result = infer(source, target)
        self.assertEqual(result["status"], "certified")
        self.assertTrue(any(f["kind"] == "le" for f in result["selected"]))
        self.assertEqual(check(source, target, cert), result)

    def test_relational_library_is_source_derived_when_nonconstant(self):
        source = (
            "class Demo { public static long f(long x) { "
            "long a = x + 3L; long b = x - 1L; return a ^ b; } }\n"
        )
        target = {
            "schema": "qkf-target-v1",
            "kind": "word_result",
            "source": {"entry": {"class": "Demo", "method": "f"}, "word_type": "long"},
            "goal": ["equals", ["xor", ["add", ["input"], ["const", 3]],
                                  ["sub", ["input"], ["const", 1]]]],
        }
        system = System(source, target)
        self.assertTrue(any(f["kind"] in {"slot_le", "slot_eq"} for f in system.features))
        cert, result = infer(source, target)
        self.assertEqual(result["status"], "certified")
        self.assertEqual(result["target_status"], "certified")
        self.assertEqual(check(source, target, cert), result)

    def test_v2_replay_does_not_import_any_producer_or_native_tool(self):
        source = (ASCENDING / "original.java").read_text(encoding="utf-8")
        cert, result = infer(source, SUCCESSOR_TARGET)
        real_import = builtins.__import__

        def guarded(name, *args, **kwargs):
            if "producer" in name or name in {"subprocess", "z3", "cvc5", "pysmt"}:
                raise AssertionError("forbidden v2 replay import: " + name)
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=guarded):
            self.assertEqual(check(source, SUCCESSOR_TARGET, cert), result)


if __name__ == "__main__":
    unittest.main()
