import builtins
from copy import deepcopy
import unittest
from unittest import mock

from research.signed_predicates.checker import check
from research.signed_predicates.frontend import CONTRACT, GOAL_SCHEMA, read_source
from research.signed_predicates.producer import derive
from research.signed_predicates.semantics import evaluate


def spec(word_type="int", target=None):
    return {
        "schema": GOAL_SCHEMA,
        "contract": CONTRACT,
        "entry": {"class": "Demo", "method": "f"},
        "word_type": word_type,
        "target": ["and", ["positive"], ["popcount_eq", 1]] if target is None else target,
    }


class SignedPredicateTests(unittest.TestCase):
    def test_positive_power_of_two_int_with_boolean_ampersand(self):
        source = (
            '@SuppressWarnings("x") class Demo { '
            'public static boolean f(int x) { return x > 0 & (x & (x - 1)) == 0; } }'
        )
        cert, result = derive(source, spec("int"))
        self.assertEqual(result["status"], "certified")
        self.assertTrue(result["all_positive_widths"])
        self.assertEqual(check(source, spec("int"), cert), result)

    def test_positive_power_of_two_long_allows_unsuffixed_one(self):
        source = (
            "class Demo { public static boolean f(long x) { "
            "return x > 0 && (x & (x - 1)) == 0; } }"
        )
        cert, result = derive(source, spec("long"))
        self.assertEqual(result["status"], "certified")
        self.assertEqual(check(source, spec("long"), cert), result)

    def test_sign_bit_only_word_is_not_positive(self):
        source = (
            "class Demo { public static boolean f(int x) { "
            "return (x & (x - 1)) == 0; } }"
        )
        cert, result = derive(source, spec("int"))
        self.assertEqual(result["status"], "refuted")
        self.assertFalse(result["all_positive_widths"])
        self.assertEqual(check(source, spec("int"), cert), result)

    def test_four_signed_zero_relations(self):
        targets = {
            ">": ["positive"],
            ">=": ["nonnegative"],
            "<": ["negative"],
            "<=": ["nonpositive"],
        }
        for op, target in targets.items():
            with self.subTest(op=op):
                source = (
                    "class Demo { public static boolean f(int x) { "
                    + "return x " + op + " 0; } }"
                )
                cert, result = derive(source, spec("int", target))
                self.assertEqual(result["status"], "certified")
                self.assertEqual(check(source, spec("int", target), cert), result)

    def test_zero_on_left_normalizes_signed_relation(self):
        source = "class Demo { public static boolean f(long x) { return 0 < x; } }"
        cert, result = derive(source, spec("long", ["positive"]))
        self.assertEqual(result["status"], "certified")

    def test_boolean_xor_is_pure_terminal_logic(self):
        source = (
            "class Demo { public static boolean f(int x) { "
            "return (x > 0) ^ (x < 0); } }"
        )
        target = ["not", ["popcount_eq", 0]]
        cert, result = derive(source, spec("int", target))
        self.assertEqual(result["status"], "certified")

    def test_arbitrary_word_order_is_still_rejected(self):
        source = (
            "class Demo { public static boolean f(int x) { "
            "return (x + 1) < (x - 1); } }"
        )
        with self.assertRaises(ValueError):
            read_source(source, {"class": "Demo", "method": "f"}, "int")

    def test_replay_does_not_import_producer_or_native_tools(self):
        source = (
            "class Demo { public static boolean f(long x) { "
            "return x > 0 && (x & (x - 1)) == 0; } }"
        )
        target = spec("long")
        cert, result = derive(source, target)
        real_import = builtins.__import__

        def guarded(name, *args, **kwargs):
            if "producer" in name or name in {"subprocess", "z3", "cvc5", "pysmt"}:
                raise AssertionError("forbidden signed replay import: " + name)
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=guarded):
            self.assertEqual(check(source, target, cert), result)


if __name__ == "__main__":
    unittest.main()
