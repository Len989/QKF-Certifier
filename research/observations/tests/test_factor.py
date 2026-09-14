"""Check factor composition, compact kernels, minimality and source binding."""
import copy
import itertools
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.observations.atomic_rows import image
from research.observations.checker import check as check_observations, replay
from research.observations.context_factor import Runner, check, consumer_model, explain
from research.observations.context_model import SCHEMA as CONTEXT_SCHEMA
from research.observations.descending_adapter import native_model, pinned_model
from research.observations.factor_producer import synthesize
from research.observations.model import MODEL_SCHEMA, Model
from research.observations.producer import synthesize as observations
from research.observations.run_factor_experiment import validate_integer_loop

ROOT = Path(__file__).resolve().parents[3]


def candidate(data, **kwargs):
    p = synthesize(data, **kwargs)
    if p["status"] != "candidate":
        raise ValueError(p)
    check(data, p["certificate"])
    return p["certificate"]


def equivalent(m, left, right):
    """Independent pair exploration, with no question or row construction."""
    pending, seen = [(left, right)], {(left, right)}
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


def consumer_sensitive():
    return {"schema": CONTEXT_SCHEMA, "contexts": ["0", "1"], "controls": ["c"],
            "alphabet": ["a", "b"], "initial_control": "c", "bottom": ["0", "1"], "boundary": "0",
            "binding": {}, "rows": [
                {"control": "c", "symbol": "a", "next_control": "c", "edges": [["0", "0"]]},
                {"control": "c", "symbol": "b", "next_control": "c", "edges": [["0", "0"], ["1", "1"]]}]}


class FactorTests(unittest.TestCase):
    def test_descending_minimal_factor_and_merge_explanations(self):
        data = pinned_model()
        cert = candidate(data)
        result = check(data, cert)
        self.assertEqual((result["residual_states"], result["classes"], result["derived_questions"]), (15, 10, 5))
        self.assertEqual((result["merged_pairs"], result["separated_class_pairs"], result["max_separator_length"]), (6, 45, 1))
        self.assertEqual((result["stored_native_cells"], result["logical_forced_cells"], result["transitions"]), (80, 8112, 80))
        self.assertTrue(result["full_context_recoverable"])
        explanation = explain(data, cert)
        self.assertEqual(len(explanation["merges"]), 6)
        model = Model(consumer_model(data, cert["context"]))
        classes = {s: i for i, b in enumerate(cert["factor"]["blocks"]) for s in b}
        for pair in explanation["merges"]:
            self.assertEqual(model.terminal[pair["left"]], model.terminal[pair["right"]])
            self.assertEqual(len(pair["obligations"]), len(model.alphabet))
            for step in pair["obligations"]:
                self.assertEqual(classes[step["left_next"]], step["shared_next_class"])
                self.assertEqual(classes[step["right_next"]], step["shared_next_class"])
        for s, t in itertools.product(model.states, repeat=2):
            self.assertEqual(classes[s] == classes[t], equivalent(model, s, t))
        self.assertFalse(Runner(data, cert).run(cert["context"]["gap"]["word"])["accepted"])

    def test_exhaustive_factor_residual_integer_agreement(self):
        data = pinned_model()
        result = validate_integer_loop(data, candidate(data))
        self.assertEqual((result["cases"], result["mismatches"]), (37448, 0))

    def test_compact_rows_match_complete_rows_and_kernels(self):
        rng = random.Random(931001)
        for _ in range(30):
            states = [str(i) for i in range(rng.randrange(1, 6))]
            data = {"schema": MODEL_SCHEMA, "states": states, "initial": states[0],
                    "alphabet": ["a", "b"], "outputs": ["0", "1"], "binding": {},
                    "terminal": {s: str(rng.randrange(2)) for s in states}, "steps": [
                        {"state": s, "symbol": a, "output": str(rng.randrange(2)), "next": rng.choice(states)}
                        for s in states for a in ["a", "b"]]}
            full = observations(data)["certificate"]
            compact = observations(data, row_encoding="atomic")["certificate"]
            check_observations(data, compact)
            self.assertEqual(full["blocks"], compact["blocks"])
            self.assertEqual(full["cells"], compact["cells"])
            k = len(compact["blocks"])
            for f, c in zip(full["rows"], compact["rows"]):
                for s in range(1 << k):
                    self.assertEqual(image(c, s, k), f["table"][s])
                    for t in range(1 << k):
                        self.assertEqual(f["table"][s] == f["table"][t],
                                         (s & c["kernel_projection"]) == (t & c["kernel_projection"]))
            self.assertEqual(replay(data, full, ["a", "b", "a"]), replay(data, compact, ["a", "b", "a"]))

    def test_compact_encoding_passes_old_eight_class_limit(self):
        n = 12
        data = {"schema": MODEL_SCHEMA, "states": [str(i) for i in range(n)], "initial": "0",
                "alphabet": ["a"], "outputs": ["tick"], "binding": {},
                "terminal": {str(i): str(int(i == 0)) for i in range(n)}, "steps": [
                    {"state": str(i), "symbol": "a", "output": "tick", "next": str((i + 1) % n)}
                    for i in range(n)]}
        self.assertEqual(observations(data)["status"], "budget_exhausted")
        with patch("research.observations.producer._row", side_effect=AssertionError("powerset expansion")):
            cert = observations(data, row_encoding="atomic")["certificate"]
        self.assertEqual(check_observations(data, cert)["classes"], n)
        self.assertEqual(len(cert["rows"][0]["supplied"]), n)
        self.assertNotIn("table", cert["rows"][0])

    def test_consumer_strengthening_and_context_recovery(self):
        data = pinned_model()
        default = candidate(data)
        strong = candidate(data, queries=data["contexts"])
        self.assertEqual(default["factor"]["blocks"], strong["factor"]["blocks"])
        self.assertEqual(check(data, strong)["classes"], 10)
        control = consumer_sensitive()
        weak = candidate(control)
        strong = candidate(control, queries=["0", "1"])
        self.assertEqual(check(control, weak)["classes"], 1)
        self.assertFalse(check(control, weak)["full_context_recoverable"])
        self.assertEqual(check(control, strong)["classes"], 2)
        self.assertTrue(check(control, strong)["full_context_recoverable"])
        self.assertTrue(Runner(control, weak).run(["a"])["accepted"])
        with self.assertRaises(ValueError):
            candidate(control, queries=["1"])
        with self.assertRaises(ValueError):
            candidate(control, queries=[])

    def test_changed_source_and_forged_bridge_hashes(self):
        data = pinned_model()
        original = candidate(data)
        source = (ROOT / "research/graal/previous/row_kernel.py").read_text()
        changed = native_model(source, ["and", ["optional"], ["comparison", [-1]]])
        mutated = candidate(changed)
        self.assertEqual(validate_integer_loop(changed, mutated, max_width=3, strict=True)["mismatches"], 0)
        def nonempty_merged_controls(d, c):
            return {frozenset(m["control"] for m in b["members"])
                    for b in explain(d, c)["classes"] if len(b["members"]) > 1 and b["recovered_contexts"]}
        self.assertEqual(nonempty_merged_controls(data, original), {frozenset({"equal", "less"})})
        self.assertEqual(nonempty_merged_controls(changed, mutated), {frozenset({"equal", "greater"})})
        with self.assertRaises(ValueError):
            check(changed, original)
        forged = copy.deepcopy(original)
        forged["context"] = mutated["context"]
        forged["context_model_sha256"] = mutated["context_model_sha256"]
        with self.assertRaises(ValueError):
            check(changed, forged)
        forged["factor"]["model_sha256"] = Model(consumer_model(changed, mutated["context"])).sha256
        with self.assertRaises(ValueError):
            check(changed, forged)

    def test_renaming_preserves_semantic_factor(self):
        data = pinned_model()
        original = candidate(data)
        def semantic_blocks(d, c, h_back=None, c_back=None):
            h_back = h_back or {h: h for h in d["contexts"]}
            c_back = c_back or {x: x for x in d["controls"]}
            return frozenset(frozenset((c_back[m["control"]], tuple(sorted(h_back[h] for h in m["allowed"])))
                                      for m in b["members"]) for b in explain(d, c)["classes"])
        expected = semantic_blocks(data, original)
        rng = random.Random(931020)
        for _ in range(20):
            changed = copy.deepcopy(data)
            maps = {}
            for field in ("contexts", "controls", "alphabet"):
                labels = [f"{field}_{i}" for i in range(len(changed[field]))]
                rng.shuffle(labels)
                maps[field] = dict(zip(changed[field], labels))
                changed[field] = labels
            h, c, a = (maps[f] for f in ("contexts", "controls", "alphabet"))
            changed["bottom"] = [h[x] for x in changed["bottom"]]
            changed["boundary"] = h[changed["boundary"]]
            changed["initial_control"] = c[changed["initial_control"]]
            for row in changed["rows"]:
                row["control"] = c[row["control"]]
                row["next_control"] = c[row["next_control"]]
                row["symbol"] = a[row["symbol"]]
                row["edges"] = [[h[x], h[y]] for x, y in row["edges"]]
                rng.shuffle(row["edges"])
            rng.shuffle(changed["rows"])
            cert = candidate(changed)
            self.assertEqual(semantic_blocks(changed, cert, {v: k for k, v in h.items()},
                                            {v: k for k, v in c.items()}), expected)
    def test_random_context_factors_against_pair_oracle(self):
        rng = random.Random(931010)
        for _ in range(80):
            contexts = [str(i) for i in range(rng.randrange(1, 4))]
            controls = [str(i) for i in range(rng.randrange(1, 4))]
            data = {"schema": CONTEXT_SCHEMA, "contexts": contexts, "controls": controls, "alphabet": ["a", "b"],
                    "initial_control": controls[0], "bottom": contexts, "boundary": contexts[0], "binding": {},
                    "rows": [{"control": c, "symbol": a, "next_control": rng.choice(controls),
                              "edges": [[h, rng.choice(contexts)] for h in contexts if rng.randrange(4)]}
                             for c in controls for a in ["a", "b"]]}
            cert = candidate(data)
            model = Model(consumer_model(data, cert["context"]))
            classes = {s: i for i, b in enumerate(cert["factor"]["blocks"]) for s in b}
            runner = Runner(data, cert)
            for s, t in itertools.product(model.states, repeat=2):
                self.assertEqual(classes[s] == classes[t], equivalent(model, s, t))
            for length in range(4):
                for word in itertools.product(model.alphabet, repeat=length):
                    _, end = model.run(model.initial, word)
                    self.assertEqual(runner.run(word)["accepted"], model.terminal[end] == "1")

    def test_budgets_never_return_a_chain_certificate(self):
        for budget in [{"max_context_states": 1}, {"max_classes": 9},
                       {"max_observations": 0}, {"max_pullbacks": 0}]:
            p = synthesize(pinned_model(), **budget)
            self.assertEqual(p["status"], "budget_exhausted")
            self.assertIsNone(p["certificate"])

    def test_factor_certificate_mutations(self):
        data = pinned_model()
        original = candidate(data)
        def alter_signature(c):
            c["factor"]["predicates"][0]["mask"] ^= 1
        mutations = {
            "outer_hash": lambda c: c.update(context_model_sha256="0" * 64),
            "context_cell": lambda c: c["context"]["cells"][0].update(next=1),
            "inner_hash": lambda c: c["factor"].update(model_sha256="0" * 64),
            "consumer": lambda c: c.update(consumer_queries=["less"]),
            "signature": alter_signature,
            "merge_membership": lambda c: c["factor"]["blocks"][0].append(c["factor"]["blocks"][1].pop()),
            "atom": lambda c: c["factor"]["rows"][0]["supplied"][0].__setitem__(1, 0),
            "empty": lambda c: c["factor"]["rows"][0].update(empty={"kind": "native"}),
            "empty_bool": lambda c: c["factor"]["rows"][0]["empty"].update(left=True),
            "extension": lambda c: c["factor"]["rows"][0].update(extension="trust-me"),
            "projection": lambda c: c["factor"]["rows"][0].update(kernel_projection=0),
            "missing_row": lambda c: c["factor"]["rows"].pop(),
            "transition": lambda c: c["factor"]["cells"][0].update(next=1),
            "initial": lambda c: c["factor"].update(initial=False),
            "separator": lambda c: c["factor"]["separators"][0].update(right_value=c["factor"]["separators"][0]["left_value"]),
            "missing_separator": lambda c: c["factor"]["separators"].pop(),
            "unknown_field": lambda c: c.update(trust_me=True),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                cert = copy.deepcopy(original)
                mutate(cert)
                with self.assertRaises(ValueError):
                    check(data, cert)

    def test_fresh_full_chain_and_cli_under_optimization(self):
        code = '''
import importlib.abc, json, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.endswith("producer") or fullname.split(".")[0] in {"z3", "pysmt", "cvc5"}:
            raise RuntimeError("forbidden checker dependency: " + fullname)
sys.meta_path.insert(0, Block())
from research.observations.context_factor import check, Runner
from research.observations.descending_adapter import pinned_model
from pathlib import Path
c=json.loads(Path(sys.argv[1]).read_text()); d=pinned_model()
r=check(d,c)
if Runner(d,c).run(c["context"]["gap"]["word"])["accepted"]:
    raise RuntimeError("lost common context")
print(json.dumps(r))
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "factor.json"
            cert = candidate(pinned_model())
            path.write_text(json.dumps(cert))
            for flags in [[], ["-O"]]:
                r = subprocess.run([sys.executable, *flags, "-c", code, str(path)], cwd=ROOT,
                                   capture_output=True, text=True, timeout=20)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(json.loads(r.stdout)["classes"], 10)
            r = subprocess.run([sys.executable, "-O", "-m", "research.observations.factor_cli",
                                "check-descending", str(path)], cwd=ROOT, capture_output=True, text=True, timeout=20)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            cert["factor"]["rows"][0]["empty"]["left"] = True
            path.write_text(json.dumps(cert))
            r = subprocess.run([sys.executable, "-O", "-c", code, str(path)], cwd=ROOT,
                               capture_output=True, text=True, timeout=20)
            self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
