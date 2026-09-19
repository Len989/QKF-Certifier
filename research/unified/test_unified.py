import builtins
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from research.observations.model import digest
from research.observations.run_package import check_package
from research.observations.target_templates import template
from research.wordexpr.frontend import goal as word_goal
from research.wordexpr.predicate_frontend import goal as predicate_goal

from .checker import check, normalize
from .experiment import (
    MAXIMUM_TARGET,
    PRED_SOURCE,
    PRED_TARGET,
    SUCCESSOR_TARGET,
    WORD_SOURCE,
    WORD_TARGET,
)
from .producer import prove
from .run import main as cli_main
from .schema import compile_target

ROOT = Path(__file__).resolve().parents[2]
TYPED = ROOT / "research/observations/evidence/typed_targets"


def load(path):
    return json.loads(Path(path).read_bytes().decode("utf-8"))


def envelope_from_typed(directory, target):
    source = (directory / "source.java").read_bytes().decode("utf-8")
    package = load(directory / "package.json")
    compiled = compile_target(target)
    retained_spec = load(directory / "goal.json")
    if digest(retained_spec) != digest(compiled["specification"]):
        raise AssertionError("unified target does not compile to retained typed goal")
    inner = check_package(source, compiled["specification"], package, profile=compiled["profile"])
    result = normalize(compiled, inner)
    envelope = {
        "schema": "qkf-unified-proof-v1",
        "kind": compiled["kind"],
        "engine": compiled["engine"],
        "binding": {
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "target_sha256": compiled["target_sha256"],
            "specification_sha256": compiled["specification_sha256"],
        },
        "proof": package,
        "result": result,
    }
    return source, envelope, result


class UnifiedTests(unittest.TestCase):
    def test_compile_word_target_matches_existing_schema(self):
        compiled = compile_target(WORD_TARGET)
        expected = {
            "schema": "qkf-word-expression-goal-v1",
            "contract": "modular-lsb-word-expressions-v1",
            "entry": {"class": "Demo", "method": "low"},
            "target": ["lowest_set_bit"],
        }
        word_goal(expected)
        self.assertEqual(compiled["specification"], expected)

    def test_compile_predicate_target_matches_existing_schema(self):
        compiled = compile_target(PRED_TARGET)
        expected = {
            "schema": "qkf-word-predicate-goal-v1",
            "contract": "modular-lsb-word-predicates-v1",
            "entry": {"class": "Demo", "method": "p"},
            "word_type": "int",
            "target": ["popcount_le", 1],
        }
        predicate_goal(expected)
        self.assertEqual(compiled["specification"], expected)

    def test_compile_observation_targets_match_templates(self):
        self.assertEqual(
            compile_target(SUCCESSOR_TARGET)["specification"],
            template("ascending", "cyclic_successor"),
        )
        self.assertEqual(
            compile_target(MAXIMUM_TARGET)["specification"],
            template("descending", "maximum"),
        )

    def test_rejects_cross_kind_fields(self):
        bad = dict(WORD_TARGET)
        bad["word_type"] = "long"
        with self.assertRaises(ValueError):
            compile_target(bad)

    def test_word_prove_and_replay(self):
        result, proof = prove(WORD_SOURCE, WORD_TARGET)
        self.assertEqual(result["status"], "certified")
        self.assertTrue(result["all_positive_widths"])
        self.assertEqual(check(WORD_SOURCE, WORD_TARGET, proof), result)

    def test_predicate_prove_and_replay(self):
        result, proof = prove(PRED_SOURCE, PRED_TARGET)
        self.assertEqual(result["status"], "certified")
        self.assertTrue(result["all_positive_widths"])
        self.assertEqual(check(PRED_SOURCE, PRED_TARGET, proof), result)

    def test_retained_successor_typed_package_replays(self):
        source, envelope, result = envelope_from_typed(
            TYPED / "ascending.original.cyclic_successor", SUCCESSOR_TARGET
        )
        self.assertEqual(result["status"], "certified")
        self.assertEqual(check(source, SUCCESSOR_TARGET, envelope), result)

    def test_retained_descending_refutation_replays(self):
        source, envelope, result = envelope_from_typed(
            TYPED / "descending.strict.maximum", MAXIMUM_TARGET
        )
        self.assertEqual(result["status"], "refuted")
        self.assertEqual(check(source, MAXIMUM_TARGET, envelope), result)

    def test_changed_target_is_rejected(self):
        result, proof = prove(WORD_SOURCE, WORD_TARGET)
        changed = json.loads(json.dumps(WORD_TARGET))
        changed["goal"] = ["equals", ["input"]]
        self.assertNotEqual(digest(changed), digest(WORD_TARGET))
        with self.assertRaises(ValueError):
            check(WORD_SOURCE, changed, proof)

    def test_check_does_not_import_producers(self):
        result, proof = prove(WORD_SOURCE, WORD_TARGET)
        real_import = builtins.__import__
        blocked = ("producer", "run_producer", "subprocess", "z3", "cvc5", "pysmt")

        def guard(name, *args, **kwargs):
            if any(part in name for part in blocked):
                raise AssertionError("forbidden replay import: " + name)
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=guard):
            self.assertEqual(check(WORD_SOURCE, WORD_TARGET, proof), result)

    def test_cli_prove_and_check(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "Demo.java"
            target = root / "target.json"
            proof = root / "proof.json"
            source.write_text(WORD_SOURCE)
            target.write_text(json.dumps(WORD_TARGET))
            self.assertEqual(
                cli_main(["prove", str(source), "--target", str(target), "--proof", str(proof)]),
                0,
            )
            self.assertTrue(proof.exists())
            self.assertEqual(
                cli_main(["check", str(source), "--target", str(target), "--proof", str(proof)]),
                0,
            )

    def test_typed_goal_identity_is_preserved(self):
        for name, target in (
            ("ascending.original.cyclic_successor", SUCCESSOR_TARGET),
            ("descending.original.maximum", MAXIMUM_TARGET),
            ("descending.strict.maximum", MAXIMUM_TARGET),
        ):
            retained = load(TYPED / name / "goal.json")
            self.assertEqual(
                digest(retained),
                digest(compile_target(target)["specification"]),
                name,
            )


if __name__ == "__main__":
    unittest.main()
