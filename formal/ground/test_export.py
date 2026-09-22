import re
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from research.ground_query.checker import check
from research.ground_query.fixtures import examples
from research.ground_query.producer import prove
from research.ground_query.schema import digest, load_json

from . import fixtures
from .export import decoded_data, export, natural, render
from .preserve import audit


class GroundExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {name: (req, cert) for name, req, cert in fixtures.positives()}

    def test_all_live_certificates_and_frozen_exports(self):
        result = fixtures.regenerate(check_only=True)
        self.assertEqual(result["positive_count"], 9)
        self.assertEqual(result["negative_count"], 28)

    def test_exact_terms_equations_events_and_goals_mapping(self):
        for name, (req, cert) in self.cases.items():
            with self.subTest(name=name):
                data, _ = export(req, cert, name)
                r, c, binding = data["request"], data["certificate"], data["binding"]
                self.assertEqual(r["equations"], req["equations"])
                self.assertEqual(c["events"], cert["events"])
                self.assertEqual(c["horizon"], cert["horizon"])
                inverse = {i: name for name, i in binding["symbol_ids"].items()}
                self.assertEqual(
                    [{"op": inverse[n["op"]], "args": n["args"]} for n in r["nodes"]], req["nodes"]
                )
                sorts = {i: name for name, i in binding["sort_ids"].items()}
                self.assertEqual(
                    {
                        inverse[i]: {
                            "args": [sorts[s] for s in spec["args"]],
                            "result": sorts[spec["result"]],
                        }
                        for i, spec in enumerate(r["signature"])
                    },
                    req["signature"],
                )
                indices = binding["positive_query_indices"]
                self.assertEqual(r["queries"], [req["queries"][i] for i in indices])
                self.assertEqual(
                    c["goals"],
                    [{k: cert["goals"][i][k] for k in ("path", "depth")} for i in indices],
                )

    def test_mixed_certificate_has_explicit_positive_projection(self):
        req, cert = self.cases["shared_typed"]
        data, _ = export(req, cert, "mixed")
        self.assertEqual(len(data["binding"]["positive_query_indices"]), 23)
        self.assertEqual(len(data["binding"]["excluded_query_indices"]), 13)
        self.assertEqual(
            sorted(
                data["binding"]["positive_query_indices"]
                + data["binding"]["excluded_query_indices"]
            ),
            list(range(36)),
        )
        self.assertTrue(
            all(
                cert["goals"][i]["status"] != "equal"
                for i in data["binding"]["excluded_query_indices"]
            )
        )

    def test_nonminimal_proof_retained_without_threshold_claim(self):
        req, cert = self.cases["flattened_nonminimal"]
        data, _ = export(req, cert, "nonminimal")
        direct, _ = prove(req)
        self.assertGreater(data["certificate"]["goals"][0]["depth"], direct["goals"][0]["depth"])
        self.assertEqual(data["certificate"]["events"], cert["events"])

    def test_changed_request_rejected(self):
        req, cert = deepcopy(self.cases["gap"])
        req["equations"].reverse()
        with self.assertRaises(ValueError):
            export(req, cert, "changed")
        with self.assertRaises(ValueError):
            decoded_data(req, cert)

    def test_invalid_certificate_rejected_before_export(self):
        req, cert = deepcopy(self.cases["gap"])
        cert["events"][0]["equation"] = 1
        with self.assertRaises(ValueError):
            export(req, cert, "false_axiom")

    def test_lemma_rule_is_not_silently_relabelled_as_axiom(self):
        req, cert = deepcopy(self.cases["gap"])
        cert["events"][0]["rule"] = "via_lemma"
        with self.assertRaises(ValueError):
            decoded_data(req, cert)

    def test_unknown_symbol_rejected(self):
        req, cert = deepcopy(self.cases["gap"])
        req["nodes"][0]["op"] = "unknown"
        cert["request_sha256"] = digest(req)
        with self.assertRaises(ValueError):
            export(req, cert, "unknown")

    def test_no_positive_goals_is_not_exported_as_success(self):
        req = dict(examples())["empty_sort"]
        cert, _ = prove(req)
        with self.assertRaises(ValueError):
            export(req, cert, "no_equality")

    def test_bool_negative_and_large_indices_rejected(self):
        for value in (False, True, -1, 2**31, "0", 0.0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                natural(value)

    def test_identifier_injection_rejected(self):
        data = decoded_data(*self.cases["gap"])
        for name in ("bad name", "x\naxiom hacked : False", "a.b", "X", "0foo"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                render(name, data)

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "duplicate.json"
            p.write_text('{"schema": "first", "schema": "second"}')
            with self.assertRaises(ValueError):
                load_json(p)

    def test_negative_population_rejected_by_existing_checker(self):
        cases = list(fixtures.negatives(self.cases))
        self.assertEqual(sum(r is not None for _, r, _, _ in cases), 23)
        for name, req, cert, _ in cases:
            if req is not None:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    check(req, cert)

    def test_export_tamper_detected_by_regeneration(self):
        files = fixtures.expected_files()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name, raw in files.items():
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(raw)
            p = root / "Examples.lean"
            p.write_bytes(p.read_bytes().replace(b".axiom 0", b".axiom 1", 1))
            with (
                patch.object(fixtures, "ROOT", root),
                self.assertRaisesRegex(ValueError, "fixture/export drift"),
            ):
                fixtures.regenerate(check_only=True)

    def test_lean_has_no_proof_holes_or_native_shortcut(self):
        for p in [*fixtures.ROOT.glob("*.lean"), *fixtures.ROOT.joinpath("Ground").glob("*.lean")]:
            with self.subTest(path=p.name):
                text = p.read_text()
                self.assertIsNone(
                    re.search(
                        r"\b(sorry|admit|native_decide|unsafe)\b|^\s*(axiom|opaque)\s", text, re.M
                    )
                )
                self.assertNotIn("decide +native", text)

    def test_axiom_audit_is_an_enforced_build_target(self):
        text = (fixtures.ROOT / "Audit.lean").read_text()
        self.assertEqual(text.count("#guard_msgs in"), 13)
        self.assertEqual(text.count("#print axioms"), 13)
        self.assertIn('"Audit"', (fixtures.ROOT / "lakefile.toml").read_text())

    def test_preserved_accepted_engine_and_suites(self):
        result = audit()
        self.assertGreater(result["preserved_files"], 2200)
        self.assertEqual(
            result["explicit_edit_exceptions"],
            [".github/workflows/direct-emission.yml", "research/regression/SUITES.json"],
        )


if __name__ == "__main__":
    unittest.main()
