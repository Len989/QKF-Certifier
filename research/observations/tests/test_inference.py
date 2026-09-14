"""Finite exact checks, semantic mutations, and a separate equivalence oracle."""
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

from research.observations.checker import check, replay
from research.observations.examples import delayed
from research.observations.model import MODEL_SCHEMA, Model
from research.observations.producer import synthesize
from research.observations.source_adapter import PROGRAM, native_model, pinned_model

ROOT = Path(__file__).resolve().parents[3]


def proposal(data, **budgets):
    p = synthesize(data, **budgets)
    if p["status"] != "candidate":
        raise ValueError(p)
    check(data, p["certificate"])
    return p["certificate"]


def native_source():
    return (ROOT / "research/graal/carry_kernel.py").read_text()


def renamed(data, seed):
    rng = random.Random(seed)
    d = copy.deepcopy(data)
    identifiers = ["state_" + str(i) for i in range(len(d["states"]))]
    rng.shuffle(identifiers)
    renaming = dict(zip(d["states"], identifiers))
    d["states"] = [renaming[s] for s in d["states"]]
    d["initial"] = renaming[d["initial"]]
    d["terminal"] = {renaming[s]: v for s, v in d["terminal"].items()}
    for row in d["steps"]:
        row["state"] = renaming[row["state"]]
        row["next"] = renaming[row["next"]]
    for field in ["states", "alphabet", "outputs", "steps"]:
        rng.shuffle(d[field])
    return d, {v: k for k, v in renaming.items()}


def equivalent_by_product_search(m, left, right):
    """Independent oracle: explore pairs until an observed difference appears."""
    pending = [(left, right)]
    seen = set(pending)
    for s, t in pending:
        if m.terminal[s] != m.terminal[t]:
            return False
        for a in m.alphabet:
            y, ss = m.step[s, a]
            z, tt = m.step[t, a]
            if y != z:
                return False
            if (ss, tt) not in seen:
                seen.add((ss, tt))
                pending.append((ss, tt))
    return True


class InferenceTests(unittest.TestCase):
    def test_carry_discovered_without_partition(self):
        data = pinned_model()
        cert = proposal(data)
        self.assertEqual(cert["blocks"], [["incremented=0,carry=0", "incremented=1,carry=1"],
                                         ["incremented=1,carry=0"]])
        summary = check(data, cert)
        self.assertEqual((summary["native_states"], summary["classes"]), (3, 2))
        self.assertEqual((summary["row_templates"], summary["supplied_cells"], summary["forced_cells"]),
                         (8, 16, 16))

    def test_manual_quotient_and_tables_are_not_executed(self):
        source = native_source()
        source += '\nraise RuntimeError("top level must not execute")\n'
        source += '\ndef quotient(phase):\n    raise RuntimeError("no supplied quotient")\n'
        self.assertEqual(proposal(native_model(source))["blocks"], proposal(pinned_model())["blocks"])

    def test_alpha_renamed_source(self):
        class Rename(ast.NodeTransformer):
            aliases = {"incremented": "started_local", "carry": "incoming_local", "g": "input_local"}
            def visit_Name(self, node):
                node.id = self.aliases.get(node.id, node.id)
                return node
            def visit_arg(self, node):
                node.arg = self.aliases.get(node.arg, node.arg)
                return node
        source = ast.unparse(Rename().visit(ast.parse(native_source())))
        old, new = pinned_model(), native_model(source)
        self.assertEqual(old["steps"], new["steps"])
        self.assertEqual(proposal(old)["blocks"], proposal(new)["blocks"])

    def test_renaming_and_input_order(self):
        for data in [pinned_model(), delayed()]:
            expected = sorted(proposal(data)["blocks"])
            for seed in range(20):
                d, inverse = renamed(data, seed)
                self.assertEqual(sorted(sorted(inverse[s] for s in b) for b in proposal(d)["blocks"]), expected)

    def test_pullback_discovers_delayed_difference(self):
        cert = proposal(delayed())
        self.assertEqual(len(cert["blocks"]), 4)
        self.assertEqual(check(delayed(), cert)["max_witness_length"], 3)
        self.assertTrue(any(p["kind"] == "pullback" for p in cert["predicates"]))

    def test_source_change_needs_three_classes(self):
        program = {**PROGRAM, "forbidden_action": "clear"}
        changed = native_model(native_source(), program)
        cert = proposal(changed)
        self.assertEqual(len(cert["blocks"]), 3)
        self.assertTrue(any(len(w["word"]) == 2 for w in cert["separators"]))
        with self.assertRaises(ValueError):
            check(changed, proposal(pinned_model()))
        forged = proposal(pinned_model())
        forged["model_sha256"] = Model(changed).sha256
        with self.assertRaisesRegex(ValueError, "kernel not stable"):
            check(changed, forged)

    def test_one_class_and_terminal_consumer(self):
        data = delayed()
        for row in data["steps"]:
            row["output"] = "0"
        self.assertEqual(len(proposal(data)["blocks"]), 1)
        data["terminal"]["3"] = "accept"
        cert = proposal(data)
        self.assertEqual(len(cert["blocks"]), 4)
        self.assertTrue(all(w["terminal"] for w in cert["separators"]))

    def test_budget_failure_is_not_a_certificate(self):
        for budget in [{"max_observations": 0}, {"max_pullbacks": 0}, {"max_classes": 1}]:
            p = synthesize(delayed(), **budget)
            self.assertEqual(p["status"], "budget_exhausted")
            self.assertIsNone(p["certificate"])

    def test_wrong_native_table_rejected(self):
        for modify in [lambda d: d["steps"].pop(), lambda d: d["states"].append(d["states"][0])]:
            data = pinned_model()
            modify(data)
            with self.assertRaises(ValueError):
                synthesize(data)

    def test_certificate_mutations(self):
        data = pinned_model()
        original = proposal(data)
        mutations = {
            "binding": lambda c: c.update(model_sha256="0" * 64),
            "missing_state": lambda c: c["blocks"][0].pop(),
            "wrong_kernel": lambda c: c["blocks"].__setitem__(slice(None), [Model(data).states]),
            "question": lambda c: c["predicates"][0].update(mask=0),
            "atom": lambda c: c["rows"][0]["supplied"][0].__setitem__(1, 3),
            "forced_step": lambda c: c["rows"][0]["steps"][0].update(image=3),
            "row_table": lambda c: c["rows"][0]["table"].__setitem__(0, 1),
            "row_kernel": lambda c: c["rows"][0].update(kernel=[[0, 1, 2, 3]]),
            "missing_row": lambda c: c["rows"].pop(),
            "transition": lambda c: c["cells"][0].update(next=1 - c["cells"][0]["next"]),
            "initial": lambda c: c.update(initial=1 - c["initial"]),
            "bool_index": lambda c: c.update(initial=False),
            "witness": lambda c: c["separators"][0].update(right_value=c["separators"][0]["left_value"]),
            "missing_witness": lambda c: c.update(separators=[]),
            "unknown_field": lambda c: c.update(trust_me=True),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                cert = copy.deepcopy(original)
                mutate(cert)
                with self.assertRaises(ValueError):
                    check(data, cert)

    def test_fresh_checker_blocks_producer_and_smt(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            (d / "model.json").write_text(json.dumps(pinned_model()))
            cert = proposal(pinned_model())
            (d / "cert.json").write_text(json.dumps(cert))
            code = '''
import importlib.abc, json, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.endswith("producer") or fullname.split(".")[0] in {"z3", "pysmt", "cvc5"}:
            raise RuntimeError("forbidden checker dependency: " + fullname)
sys.meta_path.insert(0, Block())
from research.observations.checker import check
from research.observations.source_adapter import pinned_model
from pathlib import Path
p = Path(sys.argv[1])
print(json.dumps(check(pinned_model(), json.loads((p/"cert.json").read_text()))))
'''
            for flag in [[], ["-O"]]:
                result = subprocess.run([sys.executable, *flag, "-c", code, str(d)], cwd=ROOT,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "certified")
            cert["initial"] = False
            (d / "cert.json").write_text(json.dumps(cert))
            result = subprocess.run([sys.executable, "-O", "-c", code, str(d)], cwd=ROOT,
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_random_models_against_independent_oracle(self):
        rng = random.Random(20260913)
        for number in range(120):
            n = rng.randrange(1, 7)
            states = [str(i) for i in range(n)]
            data = {"schema": MODEL_SCHEMA, "states": states, "initial": "0",
                    "alphabet": ["a", "b"], "outputs": ["0", "1"],
                    "terminal": {s: str(rng.randrange(2)) if number % 3 == 0 else "" for s in states},
                    "binding": {}, "steps": [
                        {"state": s, "symbol": a, "output": str(rng.randrange(2)),
                         "next": rng.choice(states)} for s in states for a in ["a", "b"]]}
            cert = proposal(data)
            m = Model(data)
            classes = {s: i for i, b in enumerate(cert["blocks"]) for s in b}
            for s, t in itertools.product(states, repeat=2):
                self.assertEqual(classes[s] == classes[t], equivalent_by_product_search(m, s, t))

    def test_forced_rows_execute_native_traces(self):
        data = pinned_model()
        m, cert = Model(data), proposal(data)
        for length in range(5):
            for word in itertools.product(m.alphabet, repeat=length):
                self.assertEqual(replay(data, cert, word)["outputs"], m.run(m.initial, word)[0])


if __name__ == "__main__":
    unittest.main()
