"""Shared-cut inference against explicit cut assignments and an integer loop."""
import ast
import copy
import itertools
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from research.observations.context_checker import check, accepts
from research.observations.context_model import ContextModel, SCHEMA
from research.observations.context_producer import synthesize
from research.observations.descending_adapter import native_model, pinned_model
from research.observations.run_context_experiment import decode_word, integer_pass, validate_integer_loop

ROOT = Path(__file__).resolve().parents[3]


def source():
    return (ROOT / "research/graal/previous/row_kernel.py").read_text()


def proposal(data):
    p = synthesize(data)
    if p["status"] != "candidate":
        raise ValueError(p)
    check(data, p["certificate"])
    return p["certificate"]


def run(cert, word):
    cells = {(c["state"], c["symbol"]): c["next"] for c in cert["cells"]}
    state = cert["initial"]
    for a in word:
        state = cells[state, a]
    return cert["states"][state]["accept"]


def explicit_cuts(m, word):
    """Enumerate whole assignments, never propagate a residual set backwards."""
    c = m.initial
    edges = []
    for a in word:
        c, relation = m.rows[c, a]
        edges.append(relation)
    for free in itertools.product(m.contexts, repeat=len(word)):
        cuts = list(free) + [m.boundary]
        if cuts[0] in m.members(m.bottom) and all(
                edges[i].get(cuts[i + 1]) == cuts[i] for i in range(len(word))):
            return True
    return False


class ContextTests(unittest.TestCase):
    def test_source_residuals_and_automatic_loss_witness(self):
        data = pinned_model()
        cert = proposal(data)
        result = check(data, cert)
        self.assertEqual((result["native_contexts"], result["residual_states"], result["row_templates"]), (3, 15, 24))
        self.assertEqual((result["supplied_cells"], result["forced_cells"], result["transitions"]), (72, 120, 120))
        gap = cert["gap"]
        self.assertEqual(len(gap["word"]), 2)
        self.assertEqual(decode_word(gap["word"]), {"base": 0, "optional": 1, "upper": 2, "proposed": 0})
        self.assertEqual(integer_pass(0, 1, 2, 2), 1)
        self.assertFalse(accepts(data, cert, gap["word"]))
        self.assertNotIn(gap["conflict"]["below"], gap["conflict"]["required_below"])

    def test_exhaustive_unsigned_integer_loop(self):
        data = pinned_model()
        result = validate_integer_loop(data, proposal(data))
        self.assertEqual(result["cases"], 37448)
        self.assertEqual(result["mismatches"], 0)
        self.assertEqual(result["by_width"][0]["erasure_false_accepts"], 0)
        self.assertGreater(result["by_width"][1]["erasure_false_accepts"], 0)

    def test_changed_guard_and_forged_source_binding(self):
        data = pinned_model()
        changed = native_model(source(), ["and", ["optional"], ["comparison", [-1]]])
        cert = proposal(changed)
        self.assertEqual(validate_integer_loop(changed, cert, max_width=4, strict=True)["mismatches"], 0)
        original = proposal(data)
        with self.assertRaises(ValueError):
            check(changed, original)
        original["model_sha256"] = ContextModel(changed).sha256
        with self.assertRaisesRegex(ValueError, "atoms changed"):
            check(changed, original)

    def test_old_observer_and_top_level_not_executed(self):
        poison = source() + '\nraise RuntimeError("do not execute module")\n'
        poison += '\ndef atom(*args):\n    raise RuntimeError("do not consult old P update")\n'
        original, poisoned = pinned_model(), native_model(poison)
        self.assertEqual(original["rows"], poisoned["rows"])
        self.assertEqual(proposal(original)["states"], proposal(poisoned)["states"])

    def test_changed_primitive_and_guard_domain(self):
        changed_source = source().replace("return (a>b)-(a<b)", "return (a<b)-(a>b)")
        self.assertNotEqual(source(), changed_source)
        changed = native_model(changed_source)
        original = proposal(pinned_model())
        with self.assertRaises(ValueError):
            check(changed, original)
        original["model_sha256"] = ContextModel(changed).sha256
        with self.assertRaisesRegex(ValueError, "atoms changed"):
            check(changed, original)
        with self.assertRaisesRegex(ValueError, "preserve fixed bits"):
            native_model(source(), ["comparison", [-1, 0]])

    def test_primitive_alpha_renaming(self):
        class Rename(ast.NodeTransformer):
            aliases = {"a": "left_value", "b": "right_value", "h": "higher_context",
                       "optional": "is_optional", "relation": "comparison_value"}
            def visit_Name(self, node):
                node.id = self.aliases.get(node.id, node.id)
                return node
            def visit_arg(self, node):
                node.arg = self.aliases.get(node.arg, node.arg)
                return node
        renamed = ast.unparse(Rename().visit(ast.parse(source())))
        self.assertEqual(pinned_model()["rows"], native_model(renamed)["rows"])

    def test_context_control_symbol_renaming(self):
        original = pinned_model()
        expected = proposal(original)
        rng = random.Random(20260913)
        words = [tuple(rng.choice(original["alphabet"]) for _ in range(4)) for _ in range(20)]
        for _ in range(40):
            data = copy.deepcopy(original)
            aliases = {}
            for field in ("contexts", "controls", "alphabet"):
                labels = [f"{field}_{j}" for j in range(len(data[field]))]
                rng.shuffle(labels)
                aliases[field] = dict(zip(data[field], labels))
                data[field] = labels
            h, c, a = (aliases[f] for f in ("contexts", "controls", "alphabet"))
            data["bottom"] = [h[s] for s in data["bottom"]]
            data["boundary"] = h[data["boundary"]]
            data["initial_control"] = c[data["initial_control"]]
            for row in data["rows"]:
                row["control"] = c[row["control"]]
                row["next_control"] = c[row["next_control"]]
                row["symbol"] = a[row["symbol"]]
                row["edges"] = [[h[x], h[y]] for x, y in row["edges"]]
                rng.shuffle(row["edges"])
            rng.shuffle(data["rows"])
            cert = proposal(data)
            self.assertEqual(len(cert["states"]), len(expected["states"]))
            self.assertEqual(len(cert["gap"]["word"]), 2)
            for word in words:
                self.assertEqual(run(cert, [a[s] for s in word]), run(expected, word))

    def test_random_models_against_whole_cut_assignments(self):
        rng = random.Random(2091309)
        for _ in range(100):
            contexts = [str(i) for i in range(rng.randrange(1, 4))]
            controls = [str(i) for i in range(rng.randrange(1, 4))]
            data = {"schema": SCHEMA, "contexts": contexts, "controls": controls, "alphabet": ["a", "b"],
                    "initial_control": controls[0], "bottom": [s for s in contexts if rng.randrange(2)],
                    "boundary": rng.choice(contexts), "binding": {}, "rows": [
                        {"control": c, "symbol": a, "next_control": rng.choice(controls),
                         "edges": [[h, rng.choice(contexts)] for h in contexts if rng.randrange(4)]}
                        for c in controls for a in ["a", "b"]]}
            m, cert = ContextModel(data), proposal(data)
            for length in range(5):
                for word in itertools.product(m.alphabet, repeat=length):
                    self.assertEqual(run(cert, word), explicit_cuts(m, word))

    def test_no_gap_and_single_context(self):
        data = {"schema": SCHEMA, "contexts": ["h"], "controls": ["c"], "alphabet": ["a"],
                "initial_control": "c", "bottom": ["h"], "boundary": "h", "binding": {},
                "rows": [{"control": "c", "symbol": "a", "next_control": "c", "edges": [["h", "h"]]}]}
        cert = proposal(data)
        self.assertIsNone(cert["gap"])
        self.assertEqual(len(cert["states"]), 1)
        self.assertFalse(check(data, cert)["absence_of_gap_certified"])

    def test_malformed_and_nondeterministic_native_rows(self):
        for change in [lambda d: d["rows"].pop(),
                       lambda d: d["rows"][0]["edges"].append(d["rows"][0]["edges"][0]),
                       lambda d: d.update(boundary="unknown")]:
            data = pinned_model()
            change(data)
            with self.assertRaises(ValueError):
                synthesize(data)

    def test_budget_exhaustion_does_not_certify(self):
        for budget in [{"max_states": 1}, {"max_product": 1}]:
            result = synthesize(pinned_model(), **budget)
            self.assertEqual(result["status"], "budget_exhausted")
            self.assertIsNone(result["certificate"])

    def test_certificate_mutations(self):
        data = pinned_model()
        original = proposal(data)
        mutations = {
            "binding": lambda c: c.update(model_sha256="0" * 64),
            "missing_row": lambda c: c["rows"].pop(),
            "atom": lambda c: c["rows"][0]["supplied"][0].__setitem__(1, 0),
            "forced_step": lambda c: c["rows"][0]["steps"][0].update(image=1),
            "table": lambda c: c["rows"][0]["table"].__setitem__(0, 1),
            "kernel": lambda c: c["rows"][0].update(kernel=[]),
            "state": lambda c: c["states"][0].update(allowed=0),
            "parent": lambda c: c["states"][1].update(parent={"state": 1, "symbol": "0000"}),
            "boundary": lambda c: c["states"][0].update(accept=False),
            "transition": lambda c: c["cells"][0].update(next=(c["cells"][0]["next"] + 1) % len(c["states"])),
            "missing_transition": lambda c: c["cells"].pop(),
            "duplicate_transition": lambda c: c["cells"].__setitem__(1, c["cells"][0]),
            "bool_id": lambda c: c.update(initial=False),
            "word": lambda c: c["gap"].update(word=["0000"]),
            "trace": lambda c: c["gap"]["trace"][-1].update(exact=7),
            "conflict": lambda c: c["gap"]["conflict"].update(below="equal"),
            "conflict_bool": lambda c: c["gap"]["conflict"].update(position=True),
            "unknown_field": lambda c: c.update(trust_me=True),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                cert = copy.deepcopy(original)
                mutate(cert)
                with self.assertRaises(ValueError):
                    check(data, cert)

    def test_fresh_replay_with_producer_and_smt_blocked(self):
        code = '''
import importlib.abc, json, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.endswith("producer") or fullname.split(".")[0] in {"z3", "pysmt", "cvc5"}:
            raise RuntimeError("forbidden dependency: " + fullname)
sys.meta_path.insert(0, Block())
from research.observations.context_checker import check
from research.observations.descending_adapter import pinned_model
from pathlib import Path
print(json.dumps(check(pinned_model(), json.loads(Path(sys.argv[1]).read_text()))))
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "certificate.json"
            cert = proposal(pinned_model())
            path.write_text(json.dumps(cert))
            for flags in [[], ["-O"]]:
                result = subprocess.run([sys.executable, *flags, "-c", code, str(path)], cwd=ROOT,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "certified")
            cert["gap"]["conflict"]["position"] = True
            path.write_text(json.dumps(cert))
            result = subprocess.run([sys.executable, "-O", "-c", code, str(path)], cwd=ROOT,
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
