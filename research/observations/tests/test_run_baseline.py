"""Frozen common-package regression; hashes never replace semantic replay."""
from collections import Counter
import json
import unittest

from research.observations.model import digest
from research.observations.run_package import check_package, create_package
from research.observations.run_unified_experiment import EVIDENCE, retained_cases


class CommonBaselineTests(unittest.TestCase):
    def test_all_recorded_package_identities_follow_full_replay(self):
        baseline = json.loads((EVIDENCE / "run/BASELINE.json").read_bytes().decode("utf-8"))
        self.assertEqual(baseline["schema"], "qkf-common-run-baseline-v1")
        actual = {}
        for case in retained_cases():
            package = create_package(case["source"], case["spec"], case["profile"],
                                     case["source_certificate"], case["property_certificate"])
            result = check_package(case["source"], case["spec"], package)
            encoded = (json.dumps(package, sort_keys=True, separators=(",", ":"),
                                  ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
            actual[case["id"]] = {"status": result["status"], "package_bytes": len(encoded),
                                  "package_sha256": digest(package)}
        self.assertEqual(actual, baseline["packages"])
        self.assertEqual(dict(Counter(value["status"] for value in actual.values())), baseline["counts"])


if __name__ == "__main__":
    unittest.main()
