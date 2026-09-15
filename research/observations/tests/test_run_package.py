"""Common-envelope regression and adversarial replay of both existing profiles."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from research.observations.model import digest
from research.observations.run_package import (
    RunError, check_package, create_package, explain_package, profile_for,
)
from research.observations.run_producer import verify
from research.observations.run_unified_experiment import retained_cases


def packages():
    result = {}
    for case in retained_cases():
        result[case["id"]] = {**case, "package": create_package(
            case["source"], case["spec"], case["profile"],
            case["source_certificate"], case["property_certificate"])}
    return result


def rehash_proofs(package):
    for name in ("source", "property"):
        package["binding"][name + "_certificate_sha256"] = digest(package["proofs"][name])


class CommonPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = packages()

    def rejected(self, case, package, status="invalid_certificate"):
        with self.assertRaises(RunError) as error:
            check_package(case["source"], case["spec"], package)
        self.assertEqual(error.exception.status, status)
        return str(error.exception)

    def test_all_eighteen_old_results_and_schemas_are_preserved(self):
        counts = {"certified": 0, "refuted": 0}
        for case in self.cases.values():
            result = check_package(case["source"], case["spec"], case["package"])
            self.assertEqual(result["status"], case["expected"])
            self.assertEqual(result, case["package"]["result"])
            self.assertEqual(case["package"]["proofs"]["source"], case["source_certificate"])
            self.assertEqual(case["package"]["proofs"]["property"], case["property_certificate"])
            self.assertEqual(result["source_model"]["status"], "certified")
            self.assertIs(result["scope"]["all_positive_payload_widths"], result["status"] == "certified")
            self.assertIs(result["scope"]["native_java_all_widths"], False)
            self.assertIs(result["scope"]["new_lean_theorem"], False)
            counts[result["status"]] += 1
        self.assertEqual(counts, {"certified": 11, "refuted": 7})

    def test_explanation_replays_positive_and_negative_results(self):
        for case in self.cases.values():
            result = explain_package(case["source"], case["spec"], case["package"])
            self.assertEqual(result["status"], case["expected"])
            explanation = result["explanation"]
            self.assertIs(explanation["replayed"], True)
            self.assertEqual(explanation["obligations"], case["spec"]["obligations"])
            self.assertNotEqual(explanation["chain"][0]["claim"], explanation["chain"][1]["claim"])
            if result["status"] == "refuted":
                self.assertEqual(explanation["counterexample"], result["property"]["counterexample"])

    def test_envelope_corruptions_in_both_profiles(self):
        changes = [
            lambda p: p.update(schema="unknown"),
            lambda p: p.update(profile="descending" if p["profile"] == "ascending" else "ascending"),
            lambda p: p.update(extra="not allowed"),
            lambda p: p.update(specification={"claim": "membership"}),
            lambda p: p["contracts"].update(semantics="signed Java"),
            lambda p: p["contracts"].update(source_schema="other"),
            lambda p: p["dependencies"].update(property=[]),
            lambda p: p["dependencies"].update(source=["property"]),
            lambda p: p["binding"].update(source_sha256="0" * 64),
            lambda p: p["binding"].update(specification_sha256="0" * 64),
            lambda p: p["binding"].update(source_certificate_sha256="0" * 64),
            lambda p: p["proofs"].pop("property"),
            lambda p: p["proofs"].update(property="../../elsewhere.json"),
            lambda p: p["proofs"].update(source={}),
            lambda p: p["result"].update(status="refuted"),
            lambda p: p["result"]["scope"].update(native_java_all_widths=True),
        ]
        for key in ("ascending.original.cyclic_successor", "descending.original.maximum"):
            case = self.cases[key]
            for number, change in enumerate(changes):
                altered = deepcopy(case["package"])
                change(altered)
                with self.subTest(case=key, mutation=number):
                    self.rejected(case, altered)

    def test_nested_proofs_are_checked_even_after_rehashing(self):
        for key in ("ascending.original.cyclic_successor", "descending.original.maximum"):
            case = self.cases[key]
            for layer in ("source", "property"):
                altered = deepcopy(case["package"])
                altered["proofs"][layer]["schema"] = "other"
                rehash_proofs(altered)
                self.rejected(case, altered)
            altered = deepcopy(case["package"])
            altered["proofs"]["property"]["states"].pop()
            rehash_proofs(altered)
            self.rejected(case, altered)

    def test_source_model_alone_is_never_a_target_proof(self):
        for case in self.cases.values():
            self.rejected(case, case["source_certificate"])
            altered = deepcopy(case["package"])
            altered["proofs"]["property"] = deepcopy(altered["proofs"]["source"])
            rehash_proofs(altered)
            self.rejected(case, altered)

    def test_weak_goal_cannot_be_rehashed_into_strong_goal(self):
        for weak_key, strong_key in (
            ("descending.strict.bound", "descending.strict.maximum"),
            ("ascending.first_or.membership", "ascending.first_or.cyclic_successor"),
        ):
            weak, strong = self.cases[weak_key], self.cases[strong_key]
            altered = deepcopy(weak["package"])
            goal_hash = digest(strong["spec"])
            altered["binding"]["specification_sha256"] = goal_hash
            altered["proofs"]["property"]["binding"]["specification_sha256"] = goal_hash
            rehash_proofs(altered)
            self.assertIn("protected", self.rejected(strong, altered))

    def test_rehashed_counterexample_values_are_checked(self):
        for key in ("ascending.clear_repair.cyclic_successor", "descending.plus_one.maximum"):
            case = self.cases[key]
            for field in ("output", "width", "alternative"):
                altered = deepcopy(case["package"])
                altered["proofs"]["property"]["values"][field] += 1
                rehash_proofs(altered)
                self.rejected(case, altered)
            altered = deepcopy(case["package"])
            altered["proofs"]["property"]["word"] = []
            rehash_proofs(altered)
            self.rejected(case, altered)

    def test_refutation_cannot_be_promoted_by_changing_the_summary(self):
        case = self.cases["ascending.first_or.cyclic_successor"]
        altered = deepcopy(case["package"])
        altered["result"]["status"] = "certified"
        self.assertIn("saved result", self.rejected(case, altered))
        with self.assertRaises(RunError):
            explain_package(case["source"], case["spec"], altered)

    def test_exact_source_bytes_and_external_goal_choose_profile(self):
        for key in ("ascending.original.cyclic_successor", "descending.original.maximum"):
            case = self.cases[key]
            with self.assertRaises(RunError) as error:
                check_package(case["source"] + "\n", case["spec"], case["package"])
            self.assertEqual(error.exception.status, "invalid_certificate")
            wrong = "descending" if case["profile"] == "ascending" else "ascending"
            with self.assertRaises(RunError) as error:
                check_package(case["source"], case["spec"], case["package"], profile=wrong)
            self.assertEqual(error.exception.status, "input_error")
            self.assertEqual(profile_for(case["spec"]), case["profile"])

    def test_changed_external_spec_is_an_input_error_not_a_new_assumption(self):
        case = self.cases["ascending.original.cyclic_successor"]
        for spec in (None, [], {}, {**case["spec"], "preconditions": []},
                     {**case["spec"], "schema": "unknown"}):
            with self.assertRaises(RunError) as error:
                check_package(case["source"], spec, case["package"])
            self.assertEqual(error.exception.status, "input_error")

    def test_fresh_verify_positive_and_negative_in_both_profiles(self):
        for key in ("ascending.original.cyclic_successor", "ascending.first_or.cyclic_successor",
                    "descending.original.maximum", "descending.plus_one.maximum"):
            case = self.cases[key]
            result, package = verify(case["source"], case["spec"], profile=case["profile"])
            self.assertEqual(result, case["package"]["result"])
            self.assertEqual(result, check_package(case["source"], case["spec"], package))

    def test_exhaustion_at_source_and_target_stages_has_no_package(self):
        for key, source_budget in (
            ("ascending.original.cyclic_successor", {"max_states": 1}),
            ("descending.original.maximum", {"max_contexts": 1}),
        ):
            case = self.cases[key]
            for budget in ({"source": source_budget}, {"property": {"max_states": 1}}):
                result, package = verify(case["source"], case["spec"], profile=case["profile"], budgets=budget)
                self.assertEqual(result["status"], "budget_exhausted")
                self.assertIsNone(package)
                self.assertIsNone(result["package"])

    def test_invalid_budgets_are_not_proof_failures(self):
        case = self.cases["ascending.original.cyclic_successor"]
        for budget in ([], {"extra": 1}, {"source": []}, {"property": {"max_states": True}},
                       {"source": {"max_offset": -1}}, {"property": {"max_states": 8193}},
                       {"source": {"unknown": 1}}):
            with self.assertRaises(RunError) as error:
                verify(case["source"], case["spec"], profile=case["profile"], budgets=budget)
            self.assertEqual(error.exception.status, "input_error")

    def test_unsupported_sources_do_not_refute_targets(self):
        for key in ("ascending.original.cyclic_successor", "descending.original.maximum"):
            case = self.cases[key]
            source = case["source"].replace("1L << position", "1 << position")
            result, package = verify(source, case["spec"], profile=case["profile"])
            self.assertEqual(result["status"], "unsupported")
            self.assertIsNone(package)

    def test_bad_producer_outputs_are_internal_errors(self):
        case = self.cases["ascending.original.cyclic_successor"]
        for value in (None, {"status": "certified", "certificate": {}},
                      {"status": "budget_exhausted", "certificate": {}}):
            with patch("research.observations.ascending_producer.synthesize", return_value=value):
                with self.assertRaises(RunError) as error:
                    verify(case["source"], case["spec"], profile="ascending")
                self.assertEqual(error.exception.status, "internal_error")
        with patch("research.observations.successor_producer.synthesize", return_value={
            "status": "candidate", "certificate": case["source_certificate"]
        }):
            with self.assertRaises(RunError) as error:
                verify(case["source"], case["spec"], profile="ascending")
            self.assertEqual(error.exception.status, "internal_error")


if __name__ == "__main__":
    unittest.main()
