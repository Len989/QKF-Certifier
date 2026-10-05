"""Adversarial trace checks derived from one real, tiny ordinary actor run."""

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from cold26 import validate_trace, view
from fixture26 import prepare


class Trace26Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="qkf26-trace-test-")
        cls.root = Path(cls.temporary.name)
        cls.fixture = prepare(cls.root / "fixture", 20)
        fixture_json = cls.root / "fixture.json"
        fixture_json.write_text(json.dumps(cls.fixture), encoding="utf-8")
        database = cls.root / "database.sqlite"
        shutil.copyfile(cls.fixture["db"], database)
        trace = cls.root / "trace.jsonl"
        result = subprocess.run([
            sys.executable, str(Path(__file__).with_name("actor26.py")),
            "--db", str(database), "--csv", cls.fixture["csv"],
            "--fixture-json", str(fixture_json), "--engine", "ordinary",
            "--trace", str(trace), "--kill-at", "none",
        ], capture_output=True, timeout=15)
        if result.returncode != 0:
            cls.temporary.cleanup()
            raise AssertionError(f"tiny actor failed: {result.stderr!r}")
        cls.original = [json.loads(line) for line in trace.read_text().splitlines()]
        cls.spec = {"engine": "ordinary", "kill_at": "none"}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.observations = copy.deepcopy(self.original)

    def event(self, name):
        return next(item for item in self.observations if item["event"] == name)

    def test_real_trace_accepted(self):
        events = validate_trace(self.observations, self.spec)
        self.assertEqual(events[0], "actor_started")
        self.assertEqual(events[-1], "actor_returned")

    def test_missing_after_commit_snapshot_rejected(self):
        del self.event("after_commit")["snapshot"]
        with self.assertRaises((ValueError, KeyError)):
            validate_trace(self.observations, self.spec)

    def test_forged_successful_returns_rejected(self):
        for name in ("after_commit", "after_close"):
            with self.subTest(event=name):
                self.observations = copy.deepcopy(self.original)
                self.event(name)["call_returned"] = False
                with self.assertRaisesRegex(ValueError, "successful return"):
                    validate_trace(self.observations, self.spec)

    def test_actor_treatment_binding_rejected(self):
        for name, value in (("engine", "minimal"), ("kill_at", "after_commit")):
            with self.subTest(field=name):
                self.observations = copy.deepcopy(self.original)
                self.observations[0][name] = value
                with self.assertRaisesRegex(ValueError, "treatment binding"):
                    validate_trace(self.observations, self.spec)

    def test_swapped_calls_rejected_even_with_valid_timestamps(self):
        first = next(i for i, o in enumerate(self.observations) if o["event"] == "after_commit")
        second = next(i for i, o in enumerate(self.observations) if o["event"] == "before_close")
        self.observations[first], self.observations[second] = self.observations[second], self.observations[first]
        for i, item in enumerate(self.observations):
            item.update(seq=i + 1, monotonic_ns=i * 10,
                        observation_finished_monotonic_ns=i * 10 + 1)
        with self.assertRaisesRegex(ValueError, "call order"):
            validate_trace(self.observations, self.spec)

    def test_failed_file_observation_rejected(self):
        snapshot = self.event("after_commit")["snapshot"]
        snapshot["files"]["database"]["stable_during_read"] = False
        with self.assertRaisesRegex(ValueError, "unstable/failed"):
            view(snapshot)
        with self.assertRaisesRegex(ValueError, "unstable/failed"):
            validate_trace(self.observations, self.spec)

    def test_missing_file_namespace_member_rejected(self):
        snapshot = self.event("after_commit")["snapshot"]
        del snapshot["files"]["-journal"]
        with self.assertRaisesRegex(ValueError, "census"):
            view(snapshot)

    def test_spliced_process_trace_rejected(self):
        self.event("after_commit")["pid"] += 1
        with self.assertRaisesRegex(ValueError, "PID"):
            validate_trace(self.observations, self.spec)


if __name__ == "__main__":
    unittest.main()
