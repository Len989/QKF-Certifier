"""Scope, chronology, exact premise mapping, and transport integrity attacks."""

import re
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from research.ground_query.schema import digest, load_json
from research.signed_compact import dag

from . import fixtures
from .export import export_direct, export_input, render
from .preserve import audit


class CompositionExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = {p.stem: load_json(p) for p in (fixtures.ROOT / "inputs").glob("*.json")}
        cls.decoded = {name: export_input(data) for name, data in cls.inputs.items()}

    def lemma_attack(self, mutate, name="lemma_chain"):
        d = deepcopy(self.inputs[name])
        payload = dag.unpack(d["packet"])
        mutate(payload)
        for row in payload["E_plus"]:
            row["id"] = digest({k: v for k, v in row.items() if k != "id"})
        d["packet"] = dag.pack(payload)
        with self.assertRaises((ValueError, KeyError, TypeError, IndexError)):
            export_input(d)

    def direct_attack(self, mutate):
        d = deepcopy(self.inputs["pr49_query_reuse"])
        payload = dag.unpack(d["packet"])["evidence"]
        mutate(payload)
        # Repair every dependency digest and all references, to reach the
        # semantic validation rather than fail on a stale outer hash.
        ids = {}
        for row in payload["nodes"]:
            old = row["id"]
            if row["kind"] == "equality":
                row["premises"] = [ids.get(i, i) for i in row["premises"]]
                row["via"] = ids.get(row["via"], row["via"])
            row["id"] = digest({k: v for k, v in row.items() if k != "id"})
            ids[old] = row["id"]
        for goal in payload["goals"]:
            if goal["kind"] == "node":
                goal["node"] = ids.get(goal["node"], goal["node"])
        with self.assertRaises((ValueError, KeyError, TypeError, IndexError)):
            export_direct(d["source"], d["request"]["query"], payload)

    def test_registered_scope_and_unchanged_base(self):
        r = load_json(fixtures.ROOT / "REGISTRATION.json")
        self.assertEqual(r["base"], audit()["base"])
        self.assertEqual(audit()["explicit_edit_exceptions"], ["research/regression/SUITES.json"])
        self.assertGreater(audit()["preserved_files"], 2300)

    def test_complete_reproducible_exports(self):
        m = fixtures.regenerate(check_only=True)
        self.assertEqual((m["positive_count"], m["negative_count"]), (12, 17))

    def test_original_pr49_artifact_identities(self):
        for name, data in self.inputs.items():
            if name.startswith("pr49_"):
                self.assertEqual(data["origin"]["artifact_id"], 10671870725)
                self.assertEqual(data["origin"]["packet_sha256"], digest(data["packet"]))
                self.assertEqual(
                    data["origin"]["engine"], "0be531350f1e062b04a26fd51915e443765026d5"
                )

    def test_two_chronological_lemmas_and_via_chain(self):
        raw = dag.unpack(self.inputs["lemma_chain"]["packet"])
        self.assertEqual(len(raw["E_plus"]), 2)
        self.assertEqual(raw["E_plus"][1]["via_lemma"], raw["E_plus"][0]["id"])
        self.assertEqual(raw["items"][2]["via_lemma"], raw["E_plus"][1]["id"])
        p = self.decoded["lemma_chain"]["packet"]
        self.assertEqual(len(p["assumptions"]), len(raw["E"]))
        for i, e in enumerate(p["entries"]):
            if e["kind"] == "derived":
                self.assertTrue(all(j < i for j in e["premises"]))
                self.assertTrue(e["via"] is None or e["via"] < i)

    def test_ground_events_retained_exactly(self):
        for name, d in self.inputs.items():
            if name.startswith("ground_"):
                for e in self.decoded[name]["packet"]["entries"]:
                    if e["kind"] == "derived":
                        self.assertEqual(e["certificate"]["events"], d["certificate"]["events"])

    def test_all_direct_events_retained(self):
        for name, d in self.inputs.items():
            if not name.startswith("pr49_"):
                continue
            nodes = dag.unpack(d["packet"])["evidence"]["nodes"]
            entries = self.decoded[name]["packet"]["entries"]
            self.assertEqual(len(nodes), len(entries))
            for node, entry in zip(nodes, entries):
                if node["kind"] == "equality":
                    self.assertEqual(entry["certificate"]["events"], node["proof"]["events"])
                    self.assertEqual(
                        len(entry["request"]["queries"]), len(node["request"]["queries"])
                    )

    def test_native_assumptions_are_explicit(self):
        for name, d in self.decoded.items():
            self.assertEqual(
                len(d["packet"]["assumptions"]), len(d["binding"]["native_assumptions"])
            )
            if not name.startswith("ground_"):
                self.assertTrue(
                    all(
                        "evidence" in row and "scope" in row
                        for row in d["binding"]["native_assumptions"]
                    )
                )

    def test_raw_direct_and_sdk_exports_agree(self):
        d = self.inputs["pr49_query_reuse"]
        raw = dag.unpack(d["packet"])["evidence"]
        self.assertEqual(
            export_direct(d["source"], d["request"]["query"], raw)["packet"],
            self.decoded["pr49_query_reuse"]["packet"],
        )

    def test_future_lemma_prefix_rejected(self):
        self.lemma_attack(lambda p: p["E_plus"][0].update(prior_lemmas=1))

    def test_self_support_rejected(self):
        self.lemma_attack(lambda p: p["E_plus"][0]["basis"].update(lemmas=[p["E_plus"][0]["id"]]))

    def test_missing_foundation_rejected(self):
        self.lemma_attack(lambda p: p["E"].pop(0))

    def test_wrong_via_left_endpoint_rejected(self):
        self.lemma_attack(lambda p: p["E_plus"][1]["claim"].reverse())

    def test_false_residual_rejected(self):
        self.lemma_attack(lambda p: p["E_plus"][1]["certificate"]["goals"][0].update(path=[]))

    def test_foreign_guard_rejected(self):
        d = deepcopy(self.inputs["lemma_chain"])
        for r in d["request"]["requests"]:
            r["guards"] = []
        with self.assertRaises(ValueError):
            export_input(d)

    def test_foreign_width_domain_rejected(self):
        d = deepcopy(self.inputs["lemma_parity_fixed8"])
        for r in d["request"]["requests"]:
            r["width"] = dict(kind="all_positive")
        with self.assertRaises(ValueError):
            export_input(d)

    def test_foreign_source_rejected(self):
        d = deepcopy(self.inputs["lemma_chain"])
        d["source"] = d["source"].replace("(x&7)==0", "(x&7)==1")
        with self.assertRaises(ValueError):
            export_input(d)

    def test_cached_request_mismatch_rejected(self):
        d = deepcopy(self.inputs["lemma_repeats"])
        d["request"]["requests"][1]["target"]["goal"] = ["nonnegative"]
        with self.assertRaises(ValueError):
            export_input(d)

    def test_cached_consumers_keep_their_claims(self):
        p = self.decoded["lemma_repeats"]["packet"]
        self.assertEqual(len(p["consumers"]), 3)
        self.assertEqual(p["consumers"], [p["consumers"][0]] * 3)

    def test_direct_wrong_premise_rejected_after_rehash(self):
        def change(p):
            n = next(n for n in p["nodes"] if n["kind"] == "equality" and n["premises"])
            n["premises"] = []

        self.direct_attack(change)

    def test_direct_wrong_signature_rejected_after_rehash(self):
        def change(p):
            n = next(n for n in p["nodes"] if n["kind"] == "equality")
            n["request"]["signature"]["w.input"]["result"] = "Bool"
            n["proof"]["request_sha256"] = digest(n["request"])

        self.direct_attack(change)

    def test_direct_wrong_via_rejected_after_rehash(self):
        def change(p):
            n = next(n for n in p["nodes"] if n.get("via") is not None)
            n["claim"].reverse()

        self.direct_attack(change)

    def test_sdk_interface_tamper_rejected(self):
        d = deepcopy(self.inputs["pr49_query_reuse"])
        raw = dag.unpack(d["packet"])
        raw["interface"] = {}
        d["packet"] = dag.pack(raw)
        with self.assertRaises(ValueError):
            export_input(d)

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "duplicate.json"
            path.write_text('{"format":"ground","format":"direct"}')
            with self.assertRaises(ValueError):
                load_json(path)

    def test_lean_identifier_and_numeric_injection_rejected(self):
        d = deepcopy(self.decoded["ground_gap"])
        for name in ("bad name", "x\naxiom injected : False", "Upper", "a.b"):
            with self.assertRaises(ValueError):
                render(name, d)
        for v in (True, -1, "0", 2**31):
            d["packet"]["consumers"][0]["index"] = v
            with self.assertRaises(ValueError):
                render("safe", d)

    def test_tampered_export_detected(self):
        files = fixtures.expected_files()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, raw in files.items():
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(raw)
            p = root / "CompositionExamples.lean"
            p.write_bytes(p.read_bytes().replace(b".native 0", b".native 999", 1))
            with (
                patch.object(fixtures, "ROOT", root),
                patch.object(fixtures, "expected_files", return_value=files),
            ):
                with self.assertRaisesRegex(ValueError, "fixture/export drift"):
                    fixtures.regenerate(check_only=True)

    def test_no_proof_holes_or_native_shortcuts(self):
        for p in fixtures.ROOT.rglob("*.lean"):
            if ".lake" in p.parts:
                continue
            text = p.read_text()
            self.assertIsNone(
                re.search(
                    r"\b(sorry|admit|native_decide|unsafe)\b|^\s*(axiom|opaque)\s", text, re.M
                )
            )
            self.assertNotIn("decide +native", text)

    def test_exact_axiom_audit_is_required(self):
        text = (fixtures.ROOT / "CompositionAudit.lean").read_text()
        self.assertEqual(text.count("#guard_msgs in"), 12)
        self.assertIn('"CompositionAudit"', (fixtures.ROOT / "lakefile.toml").read_text())

    def test_fresh_export_without_search_imports(self):
        code = """import importlib.abc, sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.endswith(('.producer', '.planner', '.freeze_inputs')) or fullname in ('z3',):
            raise RuntimeError('forbidden search import: ' + fullname)
sys.meta_path.insert(0, Guard())
from formal.composition.fixtures import regenerate
regenerate(check_only=True)
"""
        process = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
        )
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)


if __name__ == "__main__":
    unittest.main()
