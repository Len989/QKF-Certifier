"""Fresh-process dependency boundaries, including optimized Python replay."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research.observations.run_package import create_package
from research.observations.run_unified_experiment import retained_cases

ROOT = Path(__file__).resolve().parents[3]
GUARD = '''
import builtins
original_import = builtins.__import__
def guarded(name, *args, **kwargs):
    parts = name.split(".")
    if any(p == "producer" or p.endswith("_producer") for p in parts) or any(p in {
        "graal", "carry_adapter", "context_adapter", "ascending_validation",
        "property_validation", "word_validation", "subprocess", "z3", "cvc5",
        "pysmt", "bitwuzla", "sympy", "run_property_experiment",
        "run_ascending_experiment", "run_source_experiment"
    } for p in parts):
        raise AssertionError("prohibited replay dependency: " + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded
'''


class CommonFreshReplayTests(unittest.TestCase):
    def test_check_explain_and_rejection_without_producer_or_native_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = []
            for index, case in enumerate(retained_cases()):
                source, goal, package_path = (root / f"{index}.{suffix}" for suffix in ("java", "goal.json", "package.json"))
                source.write_bytes(case["source"].encode("utf-8"))
                goal.write_text(json.dumps(case["spec"]), encoding="utf-8")
                package = create_package(case["source"], case["spec"], case["profile"],
                                         case["source_certificate"], case["property_certificate"])
                package_path.write_text(json.dumps(package), encoding="utf-8")
                inputs.append([str(source), str(goal), str(package_path), 0 if case["expected"] == "certified" else 1])
                if case["id"] == "ascending.first_or.cyclic_successor":
                    altered = deepcopy(package)
                    altered["result"]["status"] = "certified"
                    bad = root / "forged.json"
                    bad.write_text(json.dumps(altered), encoding="utf-8")
                    inputs.append([str(source), str(goal), str(bad), 3])
            payload = root / "inputs.json"
            payload.write_text(json.dumps(inputs), encoding="utf-8")
            code = '''
import contextlib, io, json, sys
inputs = json.load(open(sys.argv[1], encoding="utf-8"))
''' + GUARD + '''
from research.observations.run import main
observed = []
for source, goal, package, expected in inputs:
    for command in ("check", "explain"):
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            actual = main([command, source, "--spec", goal, "--package", package])
        result = json.loads(captured.getvalue())
        if actual != expected:
            raise RuntimeError(str((command, actual, expected, result)))
        observed.append(result["status"])
print(json.dumps(observed))
'''
            for flags in ([], ["-O"]):
                completed = subprocess.run([sys.executable, *flags, "-c", code, str(payload)], cwd=ROOT,
                                           capture_output=True, text=True, timeout=120)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                statuses = json.loads(completed.stdout)
                self.assertEqual(len(statuses), 38)
                self.assertEqual(statuses.count("certified"), 22)
                self.assertEqual(statuses.count("refuted"), 14)
                self.assertEqual(statuses.count("invalid_certificate"), 2)

    def test_retained_envelopes_can_be_rebuilt_without_any_search(self):
        code = "import json, sys\n" + GUARD + '''
from research.observations.run_unified_experiment import run
summary = run(sys.argv[1], retained_only=True)
print(json.dumps(summary["counts"]))
'''
        with tempfile.TemporaryDirectory() as directory:
            for index, flags in enumerate(([], ["-O"])):
                output = Path(directory) / str(index)
                completed = subprocess.run([sys.executable, *flags, "-c", code, str(output)], cwd=ROOT,
                                           capture_output=True, text=True, timeout=120)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(json.loads(completed.stdout), {"certified": 11, "refuted": 7})
                self.assertEqual(len(list(output.rglob("package.json"))), 18)
                self.assertTrue((output / "MANIFEST.json").is_file())


if __name__ == "__main__":
    unittest.main()
