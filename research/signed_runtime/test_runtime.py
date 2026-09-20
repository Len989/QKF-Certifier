"""Row algebra, source binding, immutable execution and independent oracles."""
from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, is_dataclass
import io
import itertools
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from research.observations.atomic_rows import check_completion, image
from research.observations.checker import check as generic_check
from research.observations.model import digest
from research.observations.producer import synthesize
from research.signed_bridge.model import request
from research.signed_observations.producer import derive
from research.signed_observations.checker import rebuild
from research.signed_predicates.semantics import evaluate
from .core import AtomicRow, Machine
from .runtime import ExecutionLimit, Runner, load
from .cli import main

ROOT = Path(__file__).resolve().parents[2]
ENTRY = {"class": "Demo", "method": "f"}


def source(expr="x > 0 && (x & (x - 1)) == 0", typ="long"):
    return "class Demo { public static boolean f(" + typ + " x) { return " + expr + "; } }"


class RowTests(unittest.TestCase):
    def test_all_small_partial_actions_and_boolean_laws(self):
        # -1 represents a guard failure; no QKF producer is involved in oracle.
        for k in range(1, 5):
            for destinations in itertools.product(range(-1, k), repeat=k):
                row = AtomicRow(tuple(sum(1 << i for i, d in enumerate(destinations) if d == j)
                                      for j in range(k)))
                for p in range(1 << k):
                    expected = sum(1 << i for i, d in enumerate(destinations) if d >= 0 and p & (1 << d))
                    self.assertEqual(row.image(p), expected)
                    for q in range(1 << k):
                        self.assertEqual(row.image(p | q), row.image(p) | row.image(q))
                        self.assertEqual(row.image(p & q), row.image(p) & row.image(q))
                        self.assertEqual(row.same_image(p, q), row.image(p) == row.image(q))

    def test_empty_guard(self):
        row = AtomicRow((0, 0, 0))
        self.assertEqual(row.guard, 0)
        self.assertEqual(row.kernel_projection, 0)
        self.assertTrue(all(row.image(p) == 0 for p in range(8)))

    def test_single_class_native_empty_completion(self):
        for value in (0, 1):
            proof = {"supplied": [[0, 0], [1, value]], "empty": {"kind": "native"},
                     "extension": "finite-unions", "kernel_projection": value}
            check_completion(proof, 1)
            self.assertEqual(AtomicRow((value,)).image(0), image(proof, 0, 1))
        proof["supplied"][0][1] = 1
        with self.assertRaises(ValueError):
            check_completion(proof, 1)

    def test_equal_kernel_different_labels(self):
        left, right = AtomicRow((1, 2)), AtomicRow((2, 1))
        self.assertEqual(left.kernel_projection, right.kernel_projection)
        self.assertNotEqual(left.image(1), right.image(1))

    def test_rows_reject_bad_atoms(self):
        for atoms in ([], (), (True,), (-1,), (2,), (1, 1), (1, 4), (1,) * 65):
            with self.subTest(atoms=atoms), self.assertRaises(ValueError):
                AtomicRow(atoms)

    def test_row_rejects_bad_subsets_and_kernel_inputs(self):
        row = AtomicRow((1, 2))
        for arg in (True, -1, 4, 1.0, "1", None):
            with self.subTest(arg=arg):
                with self.assertRaises(ValueError):
                    row.image(arg)
                with self.assertRaises(ValueError):
                    row.same_image(0, arg)

    def test_multioutput_and_empty_guard_recovery(self):
        m = Machine(("a",), ("yes", "no", "unused"), ("t", "f"), 0,
                    ((AtomicRow((0, 1)), AtomicRow((2, 0)), AtomicRow((0, 0))),))
        self.assertEqual(m.step(0, "a"), ("yes", 1))
        self.assertEqual(m.step(1, "a"), ("no", 0))
        self.assertEqual(m.row("a", "unused").image(3), 0)

    def test_machine_rejects_missing_and_ambiguous_actions(self):
        for rows in (((AtomicRow((1, 0)),),),
                     ((AtomicRow((1, 2)), AtomicRow((1, 0))),)):
            outputs = ("a",) if len(rows[0]) == 1 else ("a", "b")
            with self.assertRaises(ValueError):
                Machine(("0",), outputs, ("t", "f"), 0, rows)

    def test_machine_rejects_bad_shapes_labels_and_root(self):
        valid = dict(alphabet=("0",), outputs=("_",), terminal=("t",), initial=0,
                     rows=((AtomicRow((1,)),),))
        changes = ({"alphabet": ["0"]}, {"alphabet": ("0", "0")}, {"outputs": (1,)},
                   {"terminal": []}, {"initial": True}, {"initial": 1}, {"rows": []},
                   {"rows": ((AtomicRow((1, 2)),),)}, {"rows": ((),)})
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                Machine(**(valid | change))

    def test_64_classes_without_powerset_expansion(self):
        row = AtomicRow(tuple(1 << i for i in range(64)))
        m = Machine(("a",), ("_",), ("terminal",) * 64, 0, ((row,),))
        for i in range(64):
            self.assertEqual(m.step(i, "a"), ("_", i))
        self.assertEqual(row.image((1 << 64) - 1), (1 << 64) - 1)
        self.assertEqual(len(m.snapshot()["rows"][0]["atoms"]), 64)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.text, self.selection = source(), request(ENTRY, "long")
        self.cert, _ = derive(self.text, self.selection)
        self.runner, self.receipt = load(self.text, self.selection, self.cert)

    def reject(self, cert, text=None, selection=None):
        with self.assertRaises((ValueError, KeyError, TypeError, IndexError)):
            load(self.text if text is None else text,
                 self.selection if selection is None else selection, cert)

    def test_checked_receipt_and_representation(self):
        self.assertEqual(self.receipt["status"], "source_runtime_verified")
        self.assertEqual(self.receipt["classes"], 5)
        self.assertEqual(self.receipt["stored_atom_images"], 10)
        for key in ("target_checked", "lean_checked", "forward_cells_retained",
                    "residual_states_retained", "powerset_tables_materialized"):
            self.assertFalse(self.receipt[key])
        self.assertEqual(self.runner.describe()["kind"], "inspection-only-not-a-certificate")

    def test_all_source_edges_recovered_from_rows(self):
        _, m, _ = rebuild(self.text, self.selection, self.cert)
        classes = {s: i for i, b in enumerate(self.cert["observations"]["blocks"]) for s in b}
        for s in m.states:
            for a in m.alphabet:
                y, t = m.step[s, a]
                self.assertEqual(self.runner.machine.step(classes[s], a), (y, classes[t]))

    def test_new_rows_match_accepted_atomic_evaluator(self):
        for proof in self.cert["observations"]["rows"]:
            row = self.runner.machine.row(proof["symbol"], proof["output"])
            for p in range(1 << self.runner.machine.classes):
                self.assertEqual(row.image(p), image(proof, p, self.runner.machine.classes))

    def test_exhaustive_ir_and_direct_factor_oracles(self):
        expressions = ("true", "false", "x < 0", "x >= 0", "x == 16", "x == 256",
                       "(x & (x - 1)) == 0", "(x + 3) < 0", "(-x) >= 0", "(~x) <= 0")
        for typ in ("int", "long"):
            for expr in expressions:
                s, r = source(expr, typ), request(ENTRY, typ)
                c, _ = derive(s, r)
                runtime, _ = load(s, r, c)
                ir, m, _ = rebuild(s, r, c)
                cells = {(p["state"], p["symbol"]): p["next"] for p in c["observations"]["cells"]}
                for w in range(1, 9):
                    for x in range(1 << w):
                        state = c["observations"]["initial"]
                        for i in range(w):
                            state = cells[state, str((x >> i) & 1)]
                        label = m.terminal[c["observations"]["blocks"][state][0]]
                        self.assertEqual(runtime.value(x, w), evaluate(ir, x, w))
                        self.assertEqual(runtime.value(x, w), label == "true")

    def test_random_registered_grammar_expressions(self):
        rng = random.Random(30001)
        for _ in range(24):
            expr = f"(x {rng.choice(('+', '-', '^', '&', '|'))} {rng.randrange(1,32)}) {rng.choice(('==','!=','<','>=','>','<='))} 0"
            s = source(expr)
            c, _ = derive(s, self.selection)
            runner, _ = load(s, self.selection, c)
            ir, _, _ = rebuild(s, self.selection, c)
            for width in (1, 7, 32, 64, 128):
                for _ in range(12):
                    x = rng.getrandbits(width)
                    self.assertEqual(runner.value(x, width), evaluate(ir, x, width))

    def test_boundaries_through_4096_bits(self):
        for w in (1, 2, 31, 32, 63, 64, 128, 256, 4096):
            for x in {0, 1, (1 << (w - 1)), (1 << w) - 1, (1 << (w - 1)) - 1}:
                positive = 0 < x < (1 << (w - 1))
                self.assertEqual(self.runner.value(x, w), positive and x.bit_count() == 1)

    def test_empty_trace_is_not_a_word(self):
        cursor = self.runner.run("")
        self.assertEqual(cursor.terminal, "not-a-word")
        self.assertEqual(cursor.width, 0)
        with self.assertRaises(ValueError):
            cursor.finish()

    def test_constant_preserves_completion_and_sign(self):
        for expression in ("true", "false", "x < 0"):
            s = source(expression)
            c, _ = derive(s, self.selection)
            runner, _ = load(s, self.selection, c)
            self.assertEqual(runner.start().terminal, "not-a-word")
            for bits in ("0", "1", "01", "10", "10101"):
                expected = expression == "true" or expression == "x < 0" and bits[-1] == "1"
                self.assertEqual(runner.run(bits).finish(), expected)

    def test_chunks_forks_and_generators(self):
        bits = "10000000"
        whole = self.runner.run(bits)
        for cut in range(len(bits) + 1):
            prefix = self.runner.start().feed(iter(bits[:cut]))
            final = prefix.feed(iter(bits[cut:]))
            self.assertEqual((final.state, final.width, final.finish()),
                             (whole.state, whole.width, whole.finish()))
        prefix = self.runner.run("1")
        self.assertFalse(prefix.finish())
        self.assertTrue(prefix.feed("0").finish())
        self.assertFalse(prefix.feed("1").finish())
        self.assertEqual(prefix.width, 1)

    def test_invalid_chunk_does_not_mutate_cursor(self):
        c = self.runner.run("1")
        for bits in ("0X", [0], [True], [None]):
            with self.assertRaises(ValueError):
                c.feed(bits)
            self.assertEqual((c.width, c.terminal), (1, "false"))

    def test_stream_budget_and_no_partial_result(self):
        c = self.runner.start()
        self.assertEqual(c.feed("", max_bits=0).width, 0)
        with self.assertRaises(ExecutionLimit):
            c.feed(itertools.repeat("0"), max_bits=10)
        self.assertEqual(c.width, 0)
        c = c.feed("10", max_bits=2)
        self.assertTrue(c.finish())
        with self.assertRaises(ExecutionLimit):
            c.feed("", max_bits=1)
        for bound in (True, -1, 1_048_577, "1"):
            with self.assertRaises(ValueError):
                c.feed("", max_bits=bound)

    def test_raw_word_type_and_bounds(self):
        for x, w in ((-1, 8), (256, 8), (True, 8), (1, True), (1, 0), (1, 4097), (1.0, 8)):
            with self.subTest(x=x, w=w), self.assertRaises(ValueError):
                self.runner.value(x, w)

    def test_step_and_row_types(self):
        for state, a in ((True, "0"), (-1, "0"), (5, "0"), (0, 0), (0, "x")):
            with self.assertRaises(ValueError):
                self.runner.machine.step(state, a)
        with self.assertRaises(ValueError):
            self.runner.machine.row("0", "missing")

    def test_deep_immutability_and_detached_inspection(self):
        with self.assertRaises(FrozenInstanceError):
            self.runner.machine.initial = 1
        with self.assertRaises(TypeError):
            self.runner.machine.rows[0][0].atoms[0] = 0
        with self.assertRaises(FrozenInstanceError):
            self.runner.identity = ()
        view = self.runner.describe()
        view["action"]["rows"][0]["atoms"].clear()
        view["identity"].clear()
        self.assertTrue(self.runner.value(1, 8))
        self.assertEqual(len(self.runner.describe()["action"]["rows"][0]["atoms"]), 5)

    def test_caller_mutation_cannot_change_loaded_runtime(self):
        before = self.runner.describe()
        self.cert.clear()
        self.selection["entry"]["method"] = "different"
        self.receipt["identity"].clear()
        self.assertEqual(before, self.runner.describe())
        self.assertTrue(self.runner.value(1, 8))

    def test_runtime_retains_no_model_proof_or_source(self):
        seen = []
        def walk(value):
            if is_dataclass(value):
                self.assertTrue(type(value).__module__.startswith("research.signed_runtime"))
                for f in fields(value):
                    walk(getattr(value, f.name))
            elif type(value) is tuple:
                for x in value:
                    walk(x)
            else:
                self.assertIn(type(value), (int, str))
                seen.append(value)
        walk(self.runner)
        self.assertNotIn(self.text, seen)
        self.assertNotIn("q000", seen)
        self.assertFalse(hasattr(self.runner.machine, "cells"))

    def test_no_source_calls_after_loading(self):
        def fail(*a, **k):
            raise AssertionError("source or checker used by hot execution")
        with patch("research.signed_runtime.runtime.rebuild", fail), \
             patch("research.signed_predicates.semantics.cell", fail), \
             patch("research.signed_predicates.semantics.evaluate", fail), \
             patch("research.signed_predicates.semantics.terminal", fail), \
             patch("research.observations.checker.check", fail):
            self.assertTrue(self.runner.value(1, 64))
            self.assertFalse(self.runner.value(128, 8))
            self.assertTrue(self.runner.run("10000000").finish())
            self.runner.describe()

    def test_load_invokes_source_chain_once(self):
        with patch("research.signed_runtime.runtime.rebuild", wraps=rebuild) as spy:
            runner, _ = load(self.text, self.selection, self.cert)
            for x in range(10):
                runner.value(x, 8)
            self.assertEqual(spy.call_count, 1)

    def test_source_request_and_ir_substitution(self):
        self.reject(self.cert, text=source("x < 0"))
        r = deepcopy(self.selection); r["word_type"] = "int"
        self.reject(self.cert, selection=r)
        c = deepcopy(self.cert); c["source_model"]["ir"] = {}
        self.reject(c)

    def test_damaged_atom_extension_empty_or_kernel(self):
        for field, value in (("supplied", [[1, 1]]), ("extension", "arbitrary"),
                             ("empty", {"kind": "native"}), ("kernel_projection", 0)):
            c = deepcopy(self.cert); c["observations"]["rows"][0][field] = value
            self.reject(c)

    def test_rows_required_and_duplicated_rows_rejected(self):
        for rows in ([], self.cert["observations"]["rows"] * 2):
            c = deepcopy(self.cert); c["observations"]["rows"] = rows
            self.reject(c)

    def test_cells_are_a_checked_obligation_not_trusted_cache(self):
        c = deepcopy(self.cert); c["observations"]["cells"][0]["next"] = c["observations"]["initial"]
        self.reject(c)
        c = deepcopy(self.cert); del c["observations"]["cells"]
        self.reject(c)

    def test_labels_cannot_be_swapped_at_fixed_kernel(self):
        c = deepcopy(self.cert)
        m = c["source_model"]["model"]
        m["terminal"] = {s: {"true": "false", "false": "true"}.get(v, v) for s, v in m["terminal"].items()}
        self.reject(c)

    def test_forged_model_with_valid_generic_proof_rejected(self):
        c = deepcopy(self.cert)
        model = c["source_model"]["model"]
        for s, label in model["terminal"].items():
            if label == "true":
                model["terminal"][s] = "false"
        c["observations"] = synthesize(model, row_encoding="atomic")["certificate"]
        self.assertEqual(generic_check(model, c["observations"])["status"], "certified")
        c["binding"]["model_sha256"] = digest(model)
        self.reject(c)

    def test_changed_source_names_keep_action_not_identity(self):
        s = self.text.replace("Demo", "Other").replace(" f(", " test(")
        r = request({"class": "Other", "method": "test"}, "long")
        c, _ = derive(s, r)
        runner, receipt = load(s, r, c)
        self.assertEqual(receipt["action_sha256"], self.receipt["action_sha256"])
        self.assertNotEqual(runner.identity, self.runner.identity)

    def test_delay_and_no_target_inference(self):
        for expr, x, w in (("x == 256", 256, 10), ("(x & (x-1)) == 0", 128, 8)):
            s = source(expr)
            c, _ = derive(s, self.selection)
            runner, receipt = load(s, self.selection, c)
            self.assertTrue(runner.value(x, w))
            self.assertFalse(receipt["target_checked"])

    def test_fresh_process_guarded_load_and_source_free_execution(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "case.json"
            p.write_text(json.dumps([self.text, self.selection, self.cert]))
            script = r'''
import builtins, json, sys
original = builtins.__import__
def guard(name, *args, **kwargs):
    if 'producer' in name or name.split('.')[0] in {'subprocess','z3','cvc5','pysmt'}:
        raise RuntimeError('forbidden import: '+name)
    return original(name, *args, **kwargs)
builtins.__import__ = guard
from research.signed_runtime.runtime import load
source, selection, proof = json.load(open(sys.argv[1]))
runner, receipt = load(source, selection, proof)
del source, selection, proof
for name in list(sys.modules):
    if name.startswith(('research.observations','research.signed_bridge','research.signed_observations','research.signed_predicates','research.wordexpr')):
        del sys.modules[name]
def trace(frame, event, arg):
    mod = frame.f_globals.get('__name__','')
    if event == 'call' and mod.startswith('research.') and not mod.startswith('research.signed_runtime'):
        raise RuntimeError('source/checker call during execution: '+mod)
sys.setprofile(trace)
if not runner.value(1,4096) or runner.value(128,8):
    raise RuntimeError('row execution mismatch')
if not runner.start().feed('1').feed('0000000').finish():
    raise RuntimeError('chunk mismatch')
runner.describe()
sys.setprofile(None)
print('source-free runtime accepted')
'''
            for flags in ([], ["-O"]):
                proc = subprocess.run([sys.executable, *flags, "-c", script, str(p)], cwd=ROOT,
                                      capture_output=True, text=True, timeout=20)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("source-free runtime accepted", proc.stdout)

    def test_64_class_source_package_loads_without_dense_rows(self):
        s = source("4611686018427387904L == 0L")
        c, _ = derive(s, self.selection)
        runner, receipt = load(s, self.selection, c)
        self.assertEqual(receipt["classes"], 64)
        self.assertEqual(receipt["stored_atom_images"], 128)
        self.assertEqual(receipt["powerset_tables_materialized"], 0)
        for w in (1, 31, 62, 63, 64, 128):
            self.assertEqual(runner.value(0, w), (4611686018427387904 & ((1 << w)-1)) == 0)

    def test_core_only_imports_standard_library(self):
        script = r"""
import builtins
original = builtins.__import__
def guard(name, *args, **kwargs):
    if name.startswith('research.') and name != 'research.signed_runtime.core':
        raise RuntimeError('non-core research import: '+name)
    return original(name, *args, **kwargs)
builtins.__import__ = guard
from research.signed_runtime.core import Machine, AtomicRow
m = Machine(('a',),('_',),('v',),0,((AtomicRow((1,)),),))
if m.step(0,'a') != ('_',0):
    raise RuntimeError('core result')
"""
        proc = subprocess.run([sys.executable, "-O", "-c", script], cwd=ROOT,
                              capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_cli_execution_inspection_and_input_errors(self):
        with tempfile.TemporaryDirectory() as td:
            s, c = Path(td) / "Demo.java", Path(td) / "proof.json"
            s.write_text(self.text); c.write_text(json.dumps(self.cert))
            common = [str(s), "--class", "Demo", "--method", "f", "--word-type", "long", "--certificate", str(c)]
            cases = [("run", ["--raw", "1", "--width", "8"], 0),
                     ("run", ["--bits", "10000000"], 0), ("inspect", [], 0),
                     ("run", ["--bits", ""], 64), ("run", [], 64),
                     ("run", ["--raw", "1"], 64), ("inspect", ["--width", "8"], 64)]
            for cmd, extra, code in cases:
                out = io.StringIO()
                with redirect_stdout(out):
                    actual = main([cmd, *common, *extra])
                self.assertEqual(actual, code, out.getvalue())
                self.assertFalse(json.loads(out.getvalue())["target_checked"])
            for text in ('{"a":1,"a":2}', '{"a":NaN}', '{}'):
                c.write_text(text)
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["inspect", *common]), 3)


if __name__ == "__main__":
    unittest.main()
