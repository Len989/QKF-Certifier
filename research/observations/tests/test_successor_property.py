"""Source-bound proofs, honest refutations, adversarial replay and CLI controls."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from research.observations.ascending_execution import integer_value
from research.observations.ascending_kernel import Runner
from research.observations.ascending_producer import synthesize as source_synthesize
from research.observations.ascending_source import extract_region
from research.observations.ascending_validation import input_word, keys, successor
from research.observations.model import digest
from research.observations.run_ascending_experiment import variants
from research.observations.successor_kernel import System, check
from research.observations.successor_producer import synthesize
from research.observations.successor_spec import specification

ROOT = Path(__file__).resolve().parents[3]


class SuccessorPropertyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = variants()
        cls.source_certificates = {}
        cls.certificates = {}
        cls.results = {}
        for name, source in cls.sources.items():
            cls.source_certificates[name] = source_synthesize(source)["certificate"]
            for claim in ("cyclic_successor", "membership"):
                spec = specification(claim)
                proposal = synthesize(source, cls.source_certificates[name], spec)
                if proposal["status"] != "candidate":
                    raise AssertionError(proposal)
                cls.certificates[name, claim] = proposal["certificate"]
                cls.results[name, claim] = check(source, cls.source_certificates[name],
                                                spec, proposal["certificate"])

    def replay(self, name, claim, certificate):
        return check(self.sources[name], self.source_certificates[name],
                     specification(claim), certificate)

    def test_original_and_irrelevant_register_are_certified(self):
        for name in ("original", "irrelevant_register"):
            result = self.results[name, "cyclic_successor"]
            self.assertEqual(result["status"], "certified")
            self.assertEqual(result["claim"], "masked_cyclic_successor")
            self.assertIs(result["all_positive_payload_widths"], True)
            self.assertEqual(result["alphabet_columns"], 6)
            self.assertEqual(result["source_factor_classes"], 2)
            self.assertEqual(result["checked_transitions"], 6 * result["closed_states"])
            for key in ("whole_helper", "native_java_all_widths", "new_lean_theorem"):
                self.assertIs(result[key], False)

    def test_mutants_have_checked_numeric_refutations(self):
        for name in ("clear_repair", "first_or", "first_four_bits"):
            result = self.results[name, "cyclic_successor"]
            self.assertEqual(result["status"], "refuted")
            self.assertIs(result["all_positive_payload_widths"], False)
            values = result["counterexample"]
            key = tuple(values[k] for k in ("width", "must", "may", "seed"))
            self.assertNotEqual(values["output"], successor(key))
            self.assertEqual(values["output"], integer_value(extract_region(self.sources[name]), key))
            self.assertEqual(len(result["checked_by"]), 3)

    def test_membership_is_distinct_and_weaker(self):
        for name in self.sources:
            self.assertEqual(self.results[name, "membership"]["status"], "certified")
        self.assertNotEqual(self.results["first_or", "membership"]["status"],
                            self.results["first_or", "cyclic_successor"]["status"])

    def test_rehashed_weak_goal_still_fails_target_obligations(self):
        certificate = deepcopy(self.certificates["first_or", "membership"])
        certificate["binding"]["specification_sha256"] = digest(specification())
        with self.assertRaisesRegex(ValueError, "protected successor"):
            self.replay("first_or", "cyclic_successor", certificate)

    def test_source_model_is_not_a_target_certificate(self):
        with self.assertRaises(ValueError):
            self.replay("original", "cyclic_successor", self.source_certificates["original"])

    def test_positive_certificate_corruptions(self):
        good = self.certificates["original", "cyclic_successor"]
        changes = [
            lambda c: c.update(schema="other"),
            lambda c: c.update(kind="model"),
            lambda c: c.update(extra=0),
            lambda c: c.pop("binding"),
            lambda c: c["binding"].update(target_rules="wrong"),
            lambda c: c["binding"].update(source_sha256="0" * 64),
            lambda c: c["binding"].update(source_certificate_sha256="0" * 64),
            lambda c: c.update(states=[]),
            lambda c: c["states"].pop(),
            lambda c: c["states"].append(deepcopy(c["states"][0])),
            lambda c: c["states"][0].update(parent=[0, "0000"]),
            lambda c: c["states"][0]["state"].__setitem__(0, True),
            lambda c: c["states"][0]["state"].__setitem__(1, 1),
            lambda c: c["states"][0]["state"].__setitem__(2, False),
            lambda c: c["states"][0]["state"].__setitem__(4, 0.0),
            lambda c: c["states"][1].update(parent=[1, "0000"]),
            lambda c: c["states"][1].update(parent=[0, "0001"]),
            lambda c: c["states"][1].update(extra=True),
        ]
        for number, change in enumerate(changes):
            altered = deepcopy(good)
            change(altered)
            with self.subTest(mutation=number), self.assertRaises((ValueError, TypeError)):
                self.replay("original", "cyclic_successor", altered)

    def test_counterexample_corruptions(self):
        good = self.certificates["clear_repair", "cyclic_successor"]
        changes = [
            lambda c: c.update(kind="closed_observation"),
            lambda c: c.update(word=[]),
            lambda c: c.update(word=["0001"]),
            lambda c: c.update(word=c["word"] * 257),
            lambda c: c.update(reason="wrap_not_minimum" if c["reason"] != "wrap_not_minimum" else "output_outside_mask"),
            lambda c: c.update(extra=0),
            lambda c: c["values"].update(width=0),
            lambda c: c["values"].update(output=c["values"]["output"] ^ 1),
            lambda c: c["values"].update(alternative=c["values"]["alternative"] ^ 1),
            lambda c: c["binding"].update(specification_sha256=digest(specification("membership"))),
        ]
        for number, change in enumerate(changes):
            altered = deepcopy(good)
            change(altered)
            with self.subTest(mutation=number), self.assertRaises((ValueError, TypeError)):
                self.replay("clear_repair", "cyclic_successor", altered)

    def test_source_and_source_certificate_are_bound(self):
        good = self.certificates["original", "cyclic_successor"]
        with self.assertRaises(ValueError):
            check(self.sources["original"] + "\n", self.source_certificates["original"], specification(), good)
        altered = deepcopy(self.source_certificates["original"])
        cell = altered["observations"]["cells"][0]
        cell["output"] = "1" if cell["output"] == "0" else "0"
        with self.assertRaises(ValueError):
            check(self.sources["original"], altered, specification(), good)
        with self.assertRaises(ValueError):
            check(self.sources["irrelevant_register"], self.source_certificates["irrelevant_register"],
                  specification(), good)

    def test_budgets_are_not_success_or_refutation(self):
        result = synthesize(self.sources["original"], self.source_certificates["original"],
                            specification(), max_states=1)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertIsNone(result["certificate"])
        result = synthesize(self.sources["clear_repair"], self.source_certificates["clear_repair"],
                            specification(), max_witness=1)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertIsNone(result["certificate"])
        for invalid in (0, True, 8193):
            with self.assertRaises(ValueError):
                synthesize(self.sources["original"], self.source_certificates["original"],
                           specification(), max_states=invalid)

    def test_integer_source_replay_is_actually_checked(self):
        with patch("research.observations.successor_kernel.integer_value", return_value=-1):
            with self.assertRaisesRegex(ValueError, "direct integer source"):
                self.replay("clear_repair", "cyclic_successor",
                            self.certificates["clear_repair", "cyclic_successor"])

    def test_mask_breaking_source_is_not_filtered_out(self):
        source = self.sources["original"]
        region = extract_region(source)["code"]
        self.assertEqual(region.count("newLowerBound |= bit;"), 1)
        source = source.replace(region, region.replace("newLowerBound |= bit;", "newLowerBound &= ~bit;"))
        source_certificate = source_synthesize(source)["certificate"]
        spec = specification("membership")
        proposal = synthesize(source, source_certificate, spec)
        result = check(source, source_certificate, spec, proposal["certificate"])
        self.assertEqual(result["status"], "refuted")
        self.assertEqual(result["reason"], "output_outside_mask")

    def test_actual_factors_and_targets_against_bounded_numeric_oracle(self):
        for name, source in self.sources.items():
            system = System(source, self.source_certificates[name], specification())
            runner = Runner(source, self.source_certificates[name])
            region = extract_region(source)
            for key in keys(4):
                width, must, may, seed = key
                output = sum(int(y) << i for i, y in enumerate(runner.run(input_word(key))["outputs"]))
                self.assertEqual(output, integer_value(region, key))
                legal = [z for z in range(1 << width) if z & must == must and not z & ~may]
                reasons = []
                for alternative in legal:
                    word = [c + str((alternative >> i) & 1) for i, c in enumerate(input_word(key))]
                    state, _ = system.trace(word)
                    reasons.append(system.bad(state))
                self.assertEqual(all(reason is None for reason in reasons), output == successor(key))

    def test_fresh_replay_without_search_smt_or_native_imports(self):
        packages = [[self.sources[name], self.source_certificates[name], specification(claim), certificate]
                    for (name, claim), certificate in self.certificates.items()]
        code = '''
import builtins, json, sys
packages = json.load(open(sys.argv[1], encoding="utf-8"))
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
from research.observations.successor_kernel import check
print(json.dumps([check(*p)["status"] for p in packages]))
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packages.json"
            path.write_text(json.dumps(packages), encoding="utf-8")
            expected = [self.results[key]["status"] for key in self.certificates]
            for flags in ([], ["-O"]):
                result = subprocess.run([sys.executable, *flags, "-c", code, str(path)], cwd=ROOT,
                                        text=True, capture_output=True, timeout=45)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), expected)

    def test_cli_verdicts_and_independent_spec_argument(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def run(*args):
                result = subprocess.run([sys.executable, "-m", "research.observations.successor_cli", *map(str, args)],
                                        cwd=ROOT, text=True, capture_output=True, timeout=30)
                return result.returncode, json.loads(result.stdout)
            spec_path = root / "spec.json"
            self.assertEqual(run("spec", spec_path)[0], 0)
            for name, expected in (("original", 0), ("clear_repair", 1)):
                source_path = root / (name + ".java")
                source_path.write_bytes(self.sources[name].encode("utf-8"))
                source_cert = root / (name + ".source.json")
                source_cert.write_text(json.dumps(self.source_certificates[name]), encoding="utf-8")
                cert = root / (name + ".target.json")
                common = [source_path, "--source-certificate", source_cert, "--spec", spec_path, "--certificate", cert]
                self.assertEqual(run("derive", *common)[0], expected)
                self.assertEqual(run("check", *common)[0], expected)
                saved = cert.read_bytes()
                self.assertEqual(run("derive", *common)[0], 3)
                self.assertEqual(cert.read_bytes(), saved)
            self.assertEqual(run("check", source_path, "--source-certificate", source_cert,
                                 "--certificate", cert)[0], 3)
            cert.write_text("{}", encoding="utf-8")
            self.assertEqual(run("check", *common)[0], 3)

    def test_cli_budgets_and_output_files_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.java"
            source.write_bytes(self.sources["original"].encode("utf-8"))
            source_cert = root / "source.json"
            source_cert.write_text(json.dumps(self.source_certificates["original"]), encoding="utf-8")
            spec = root / "spec.json"
            spec.write_text(json.dumps(specification()), encoding="utf-8")
            base = [sys.executable, "-m", "research.observations.successor_cli", "derive", str(source),
                    "--source-certificate", str(source_cert), "--spec", str(spec)]
            output = root / "not-created.json"
            result = subprocess.run(base + ["--certificate", str(output), "--max-states", "1"],
                                    cwd=ROOT, text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertFalse(output.exists())
            for path in (source, source_cert, spec):
                before = path.read_bytes()
                result = subprocess.run(base + ["--certificate", str(path)], cwd=ROOT,
                                        text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
