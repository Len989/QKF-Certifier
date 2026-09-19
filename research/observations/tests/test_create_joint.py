import builtins
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest import mock

from research.observations.create_kernel import CARRIER, check
from research.observations.create_math import equivalent_result, execute_create, exact_extrema
from research.observations.create_producer import synthesize
from research.observations.create_source import FIXTURE, read_source
from research.observations.create_spec import specification
from research.observations.create_validation import exhaustive_small

SOURCE = FIXTURE.read_text(encoding="utf-8")
SPEC = specification()


class CreateJointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        proposal = synthesize(SOURCE, SPEC)
        if proposal.get("status") != "candidate":
            raise AssertionError(proposal)
        cls.certificate = proposal["certificate"]
        cls.result = check(SOURCE, SPEC, cls.certificate)

    def test_fixture_source_binding(self):
        bound = read_source(SOURCE)
        self.assertEqual(bound["schema"], "qkf-graal-create-source-v1")
        self.assertEqual(bound["empty_factory"]["kind"], "direct")
        self.assertEqual(len(bound["methods"]), 14)

    def test_fresh_joint_certificate(self):
        self.assertEqual(self.result["status"], "certified")
        self.assertEqual(self.result["carrier_states"], 4)
        self.assertEqual(self.certificate["carrier"], CARRIER)
        self.assertEqual(
            self.result["stabilization"]["updates_before_fixed_point_at_most"], 2
        )

    def test_changed_iteration_limit_rejected(self):
        changed = SOURCE.replace("ITERATION_LIMIT=3", "ITERATION_LIMIT=4", 1)
        with self.assertRaises(ValueError):
            read_source(changed)
        with self.assertRaises(ValueError):
            check(changed, SPEC, self.certificate)

    def test_changed_create_body_rejected(self):
        changed = SOURCE.replace(
            "lowerBoundTmp > upperBoundTmp",
            "lowerBoundTmp >= upperBoundTmp",
            1,
        )
        with self.assertRaises(ValueError):
            read_source(changed)

    def test_changed_spec_rejected(self):
        changed = deepcopy(SPEC)
        changed["claim"] = "weaker_claim"
        with self.assertRaises(ValueError):
            check(SOURCE, changed, self.certificate)

    def test_changed_carrier_rejected(self):
        broken = deepcopy(self.certificate)
        broken["carrier"][1]["facts"].pop()
        with self.assertRaises(ValueError):
            check(SOURCE, SPEC, broken)

    def test_changed_dependency_rejected(self):
        broken = deepcopy(self.certificate)
        package = broken["dependencies"]["descending"]
        package["result"]["status"] = "refuted"
        # Even recomputing the outer dependency digest cannot promote corruption.
        from research.observations.model import digest

        broken["dependencies_sha256"] = digest(broken["dependencies"])
        with self.assertRaises(ValueError):
            check(SOURCE, SPEC, broken)

    def test_replay_never_imports_producers_or_native_tools(self):
        real_import = builtins.__import__
        blocked = ("producer", "subprocess", "z3", "cvc5", "pysmt")

        def guarded(name, *args, **kwargs):
            if any(part in name for part in blocked):
                raise AssertionError("forbidden create replay import: " + name)
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=guarded):
            self.assertEqual(check(SOURCE, SPEC, self.certificate), self.result)

    def test_known_three_iteration_control(self):
        item = {
            "bits": 4, "lower": -8, "upper": -6,
            "must": 1, "may": 11, "can_zero": False,
        }
        result = execute_create(item)
        self.assertEqual(result["kind"], "value")
        self.assertEqual(result["iterations"], 3)
        self.assertTrue(equivalent_result(item, result))

    def test_zero_hole_becomes_empty(self):
        item = {
            "bits": 8, "lower": 0, "upper": 0,
            "must": 0, "may": 0, "can_zero": False,
        }
        result = execute_create(item)
        self.assertEqual(result["kind"], "empty")
        self.assertEqual(exact_extrema(item), (None, None))
        self.assertTrue(equivalent_result(item, result))

    def test_signed_64_digit_dp(self):
        item = {
            "bits": 64,
            "lower": -17,
            "upper": 19,
            "must": 5,
            "may": (1 << 64) - 3,
            "can_zero": False,
        }
        result = execute_create(item)
        self.assertTrue(equivalent_result(item, result))
        lo, hi = exact_extrema(item)
        self.assertEqual((result["lower"], result["upper"]), (lo, hi))

    def test_small_exhaustive_control(self):
        result = exhaustive_small(3)
        self.assertEqual(result["mismatches"], 0)
        self.assertGreater(result["inputs"], 1000)


if __name__ == "__main__":
    unittest.main()
