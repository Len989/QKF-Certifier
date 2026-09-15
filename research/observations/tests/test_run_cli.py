"""End-to-end CLI contract, error classification and input-file preservation."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from research.observations.run import main
from research.observations.run_io import read_json, read_source
from research.observations.run_package import RunError, create_package
from research.observations.run_unified_experiment import retained_cases

ROOT = Path(__file__).resolve().parents[3]


class CommonCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {}
        for case in retained_cases():
            cls.cases[case["id"]] = {**case, "package": create_package(
                case["source"], case["spec"], case["profile"],
                case["source_certificate"], case["property_certificate"])}

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def invoke(self, *args):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(list(map(str, args)))
        text = stdout.getvalue()
        self.assertEqual(len(text.splitlines()), 1, text[:500])
        return code, json.loads(text)

    def fixture(self, key):
        case = self.cases[key]
        directory = self.root / key
        directory.mkdir(exist_ok=True)
        (directory / "source.java").write_bytes(case["source"].encode("utf-8"))
        for filename, value in (("goal.json", case["spec"]), ("package.json", case["package"]),
                                ("model.json", case["source_certificate"]),
                                ("property.json", case["property_certificate"])):
            (directory / filename).write_text(json.dumps(value), encoding="utf-8")
        return directory

    def test_check_and_explain_all_eighteen_packages(self):
        for key, case in self.cases.items():
            directory = self.fixture(key)
            for command in ("check", "explain"):
                code, result = self.invoke(command, directory / "source.java", "--spec", directory / "goal.json",
                                           "--package", directory / "package.json")
                self.assertEqual(code, 0 if case["expected"] == "certified" else 1)
                self.assertEqual(result["status"], case["expected"])
                if command == "explain":
                    self.assertTrue(result["explanation"]["replayed"])

    def test_four_target_templates_are_not_proof_results(self):
        for key in ("descending.original.maximum", "descending.original.bound",
                    "ascending.original.cyclic_successor", "ascending.original.membership"):
            case = self.cases[key]
            output = self.root / (key + ".json")
            code, result = self.invoke("spec", output, "--profile", case["profile"], "--claim", case["spec"]["claim"])
            self.assertEqual((code, result["status"]), (0, "written"))
            self.assertEqual(json.loads(output.read_text()), case["spec"])
            before = output.read_bytes()
            self.assertEqual(self.invoke("spec", output, "--profile", case["profile"],
                                         "--claim", case["spec"]["claim"])[0], 64)
            self.assertEqual(output.read_bytes(), before)

    def test_verify_generates_replayable_packages_and_preserves_existing_output(self):
        for key in ("descending.original.maximum", "ascending.first_or.cyclic_successor"):
            case = self.cases[key]
            directory = self.fixture(key)
            output = directory / "fresh"
            args = [directory / "source.java", "--spec", directory / "goal.json",
                    "--profile", case["profile"], "--output", output]
            code, result = self.invoke("verify", *args)
            self.assertEqual(code, 0 if case["expected"] == "certified" else 1)
            self.assertEqual(result["status"], case["expected"])
            package_path = output / "package.json"
            before = package_path.read_bytes()
            checked = self.invoke("check", directory / "source.java", "--spec", directory / "goal.json",
                                  "--package", package_path)
            self.assertEqual(checked, (code, result))
            self.assertEqual(self.invoke("verify", *args)[0], 64)
            self.assertEqual(package_path.read_bytes(), before)

    def test_missing_external_goal_or_profile_is_an_argument_error(self):
        for args in ((), ("check", "source.java", "--package", "package.json"),
                     ("explain", "source.java", "--package", "package.json"),
                     ("verify", "source.java", "--spec", "goal.json", "--output", "out"),
                     ("spec", "goal.json", "--profile", "ascending", "--claim", "maximum")):
            code, result = self.invoke(*args)
            self.assertEqual((code, result["status"]), (64, "input_error"))

    def test_profile_conflicts_and_package_profile_substitution(self):
        directory = self.fixture("ascending.original.cyclic_successor")
        common = [directory / "source.java", "--spec", directory / "goal.json",
                  "--package", directory / "package.json"]
        self.assertEqual(self.invoke("check", *common, "--profile", "descending")[0], 64)
        package = json.loads((directory / "package.json").read_text())
        package["profile"] = "descending"
        (directory / "package.json").write_text(json.dumps(package))
        self.assertEqual(self.invoke("check", *common)[0], 3)

    def test_malformed_package_json_is_not_a_refutation(self):
        directory = self.fixture("ascending.original.cyclic_successor")
        for text in ('{', '{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '[' * 2000 + ']' * 2000):
            (directory / "package.json").write_text(text)
            code, result = self.invoke("check", directory / "source.java", "--spec", directory / "goal.json",
                                       "--package", directory / "package.json")
            self.assertEqual((code, result["status"]), (3, "invalid_certificate"))

    def test_bad_input_encoding_and_goal_json_are_input_errors(self):
        directory = self.fixture("ascending.original.cyclic_successor")
        args = [directory / "source.java", "--spec", directory / "goal.json",
                "--package", directory / "package.json"]
        for text in ('{', '{"schema":"a","schema":"b"}', '{"x":NaN}'):
            (directory / "goal.json").write_text(text)
            self.assertEqual(self.invoke("check", *args)[0], 64)
        (directory / "goal.json").write_text(json.dumps(self.cases["ascending.original.cyclic_successor"]["spec"]))
        (directory / "source.java").write_bytes(b'\xff')
        self.assertEqual(self.invoke("check", *args)[0], 64)

    def test_missing_files_and_transport_limits(self):
        directory = self.fixture("ascending.original.cyclic_successor")
        self.assertEqual(self.invoke("check", directory / "source.java", "--spec", directory / "goal.json",
                                     "--package", directory / "absent.json")[0], 64)
        with patch("research.observations.run_io.MAX_PACKAGE_BYTES", 2):
            with self.assertRaises(RunError) as error:
                read_json(directory / "package.json", package=True)
            self.assertEqual(error.exception.status, "invalid_certificate")
        with patch("research.observations.run_io.MAX_SOURCE_BYTES", 2):
            with self.assertRaises(RunError) as error:
                read_source(directory / "source.java")
            self.assertEqual(error.exception.status, "input_error")

    def test_source_newlines_are_bound_exactly(self):
        directory = self.fixture("ascending.original.cyclic_successor")
        path = directory / "source.java"
        original = path.read_bytes()
        path.write_bytes(original.replace(b'\n', b'\r\n'))
        self.assertEqual(read_source(path).encode("utf-8"), path.read_bytes())
        self.assertEqual(self.invoke("check", path, "--spec", directory / "goal.json",
                                     "--package", directory / "package.json")[0], 3)

    def test_inputs_directories_and_symlinks_are_not_overwritten(self):
        directory = self.fixture("ascending.original.cyclic_successor")
        common = [directory / "source.java", "--profile", "ascending", "--spec", directory / "goal.json"]
        for path in (directory / "source.java", directory / "goal.json", directory / "package.json"):
            before = path.read_bytes()
            self.assertEqual(self.invoke("verify", *common, "--output", path)[0], 64)
            self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.invoke("verify", *common, "--output", directory)[0], 64)
        link = directory / "dangling"
        try:
            link.symlink_to(directory / "missing")
        except (NotImplementedError, OSError):
            return
        self.assertEqual(self.invoke("verify", *common, "--output", link)[0], 64)
        self.assertTrue(link.is_symlink())
        self.assertFalse((directory / "missing").exists())

    def test_exhaustion_and_unsupported_create_reports_not_certificates(self):
        directory = self.fixture("ascending.original.cyclic_successor")
        common = [directory / "source.java", "--profile", "ascending", "--spec", directory / "goal.json"]
        budget = directory / "budget.json"
        budget.write_text(json.dumps({"property": {"max_states": 1}}))
        output = directory / "exhausted"
        code, result = self.invoke("verify", *common, "--budget", budget, "--output", output)
        self.assertEqual((code, result["status"]), (2, "budget_exhausted"))
        self.assertFalse((output / "package.json").exists())
        self.assertTrue((output / "result.json").is_file())
        source = directory / "source.java"
        source.write_bytes(source.read_bytes().replace(b'1L << position', b'1 << position'))
        output = directory / "unsupported"
        code, result = self.invoke("verify", *common, "--output", output)
        self.assertEqual((code, result["status"]), (4, "unsupported"))
        self.assertFalse((output / "package.json").exists())

    def test_bad_budgets_and_search_flags_at_replay_are_rejected(self):
        directory = self.fixture("ascending.original.cyclic_successor")
        budget = directory / "budget.json"
        budget.write_text(json.dumps({"property": {"max_states": True}}))
        output = directory / "bad-budget"
        self.assertEqual(self.invoke("verify", directory / "source.java", "--spec", directory / "goal.json",
                                     "--profile", "ascending", "--budget", budget, "--output", output)[0], 64)
        self.assertFalse(output.exists())
        self.assertEqual(self.invoke("check", directory / "source.java", "--spec", directory / "goal.json",
                                     "--package", directory / "package.json", "--budget", budget)[0], 64)

    def test_package_can_move_without_following_embedded_paths(self):
        directory = self.fixture("ascending.original.cyclic_successor")
        moved = self.root / "relocated.json"
        moved.write_bytes((directory / "package.json").read_bytes())
        (directory / "package.json").unlink()
        self.assertEqual(self.invoke("check", directory / "source.java", "--spec", directory / "goal.json",
                                     "--package", moved)[0], 0)

    def test_unexpected_exception_has_distinct_internal_error_exit(self):
        with patch("research.observations.run.execute", side_effect=RuntimeError("test fault")):
            code, result = self.invoke("spec", self.root / "unused.json", "--profile", "ascending", "--claim", "membership")
        self.assertEqual((code, result["status"]), (70, "internal_error"))
        self.assertFalse((self.root / "unused.json").exists())

    def test_original_property_clis_still_replay_embedded_certificates(self):
        for key, module in (("ascending.first_or.cyclic_successor", "successor_cli"),
                            ("descending.original.maximum", "property_cli")):
            case = self.cases[key]
            directory = self.fixture(key)
            completed = subprocess.run([sys.executable, "-O", "-m", "research.observations." + module,
                                        "check", str(directory / "source.java"),
                                        "--source-certificate", str(directory / "model.json"),
                                        "--spec", str(directory / "goal.json"),
                                        "--certificate", str(directory / "property.json")],
                                       cwd=ROOT, capture_output=True, text=True, timeout=45)
            self.assertEqual(completed.returncode, 0 if case["expected"] == "certified" else 1, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["status"], case["expected"])


if __name__ == "__main__":
    unittest.main()
