"""Frozen certificates are replayed against independently chosen targets."""
from copy import deepcopy
import json
import subprocess
import sys
import unittest

from research.observations.replay_successor_evidence import ROOT, SNAPSHOT, replay


class SuccessorEvidenceTests(unittest.TestCase):
    def test_retained_population_replays(self):
        results = replay(json.loads(SNAPSHOT.read_bytes().decode("utf-8")))
        self.assertEqual(len(results), 5)
        self.assertEqual(sum(r["status"] == "refuted" for v in results.values() for r in v.values()), 3)
        for name in ("original", "irrelevant_register"):
            self.assertEqual(results[name]["cyclic_successor"]["closed_states"], 8)
            self.assertEqual(results[name]["cyclic_successor"]["checked_transitions"], 48)

    def test_snapshot_cannot_change_goals_paths_or_inputs(self):
        original = json.loads(SNAPSHOT.read_bytes().decode("utf-8"))
        changes = [
            lambda s: s["specifications"].pop("cyclic_successor"),
            lambda s: s["specifications"]["cyclic_successor"].update(obligations=[]),
            lambda s: s["cases"].pop("first_or"),
            lambda s: s["cases"]["original"].update(source="../other.java"),
            lambda s: s["cases"]["original"].update(source_sha256="0" * 64),
            lambda s: s["cases"]["original"].update(source_certificate_sha256="0" * 64),
        ]
        for change in changes:
            altered = deepcopy(original)
            change(altered)
            with self.assertRaises(ValueError):
                replay(altered)

    def test_frozen_replay_with_dependency_blockers_and_optimization(self):
        code = '''
import builtins, runpy
original_import = builtins.__import__
def guarded(name, *args, **kwargs):
    parts = name.split(".")
    if any("producer" in p or p.startswith("run_") for p in parts) or any(p in {
        "graal", "ascending_validation", "carry_adapter", "context_adapter",
        "subprocess", "z3", "cvc5", "pysmt", "bitwuzla", "sympy"
    } for p in parts):
        raise AssertionError("forbidden replay dependency: " + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded
runpy.run_module("research.observations.replay_successor_evidence", run_name="__main__")
'''
        for flags in ([], ["-O"]):
            result = subprocess.run([sys.executable, *flags, "-c", code], cwd=ROOT,
                                    text=True, capture_output=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "replayed")


if __name__ == "__main__":
    unittest.main()
