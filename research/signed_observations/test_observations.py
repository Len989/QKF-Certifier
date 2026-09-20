"""Source binding, checked closure, independent finite oracle and hostile data."""
from collections import deque
from contextlib import redirect_stdout
from copy import deepcopy
import io
import itertools
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from research.observations.checker import check as check_generic, replay
from research.observations.model import Model, digest
from research.observations.producer import synthesize
from research.signed_bridge.model import EMPTY, request
from research.signed_predicates.semantics import evaluate
from research.wordexpr.frontend import Unsupported
from .checker import binding, check, rebuild
from .cli import main
from .explain import explain
from .producer import derive

ROOT = Path(__file__).resolve().parents[2]
ENTRY = {"class": "Demo", "method": "f"}


def source(expression="x > 0 && (x & (x - 1)) == 0", typ="long"):
    return "class Demo { public static boolean f(" + typ + " x) { return " + expression + "; } }"


def inequivalent_pairs(m):
    """Independent pair-state greatest-bisimulation complement; no questions."""
    bad = {(s, t) for s in m.states for t in m.states
           if m.terminal[s] != m.terminal[t] or any(m.step[s, a][0] != m.step[t, a][0] for a in m.alphabet)}
    while True:
        new = {(s, t) for s in m.states for t in m.states
               if any((m.step[s, a][1], m.step[t, a][1]) in bad for a in m.alphabet)}
        if new <= bad:
            return bad
        bad |= new


def shortest_terminal_separator(m, left, right):
    queue, seen = deque([(left, right, [])]), {(left, right)}
    while queue:
        l, r, word = queue.popleft()
        if m.terminal[l] != m.terminal[r]:
            return word
        for a in m.alphabet:
            pair = (m.step[l, a][1], m.step[r, a][1])
            if pair not in seen:
                seen.add(pair)
                queue.append((*pair, word + [a]))
    return None


def factor_value(m, proof, x, width):
    # A test oracle using the fully checked cells; not a new public executor.
    edges = {(c["state"], c["symbol"]): c["next"] for c in proof["cells"]}
    state = proof["initial"]
    for i in range(width):
        state = edges[state, str((x >> i) & 1)]
    return m.terminal[proof["blocks"][state][0]] == "true"


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.source, self.selection = source(), request(ENTRY, "long")
        self.cert, self.result = derive(self.source, self.selection)

    def reject(self, c):
        with self.assertRaises((ValueError, KeyError, TypeError, IndexError)):
            check(self.source, self.selection, c)

    def oracle(self, s, r):
        c, result = derive(s, r)
        self.assertIsNotNone(c)
        _, m, _ = rebuild(s, r, c)
        bad = inequivalent_pairs(m)
        classes = {s: i for i, block in enumerate(c["observations"]["blocks"]) for s in block}
        for left in m.states:
            for right in m.states:
                self.assertEqual(classes[left] != classes[right], (left, right) in bad)
        return c, result, m

    def test_scope_and_checked_roundtrip(self):
        result = {k: v for k, v in self.result.items() if k != "discovery"}
        self.assertEqual(check(self.source, self.selection, self.cert), result)
        self.assertEqual(result["status"], "source_observation_verified")
        self.assertEqual(result["claim"], "source_observation_equivalence")
        self.assertFalse(result["target_checked"])
        self.assertFalse(result["lean_checked"])
        self.assertFalse(result["minimum_question_count_claimed"])
        self.assertFalse(result["shortest_witnesses_claimed"])
        self.assertEqual((result["model_states"], result["classes"], result["positive_classes"]), (6, 5, 4))

    def test_exact_reuse_of_existing_producer(self):
        expected = synthesize(self.cert["source_model"]["model"], row_encoding="atomic")
        self.assertEqual(expected["certificate"], self.cert["observations"])
        self.assertEqual(self.result["discovery"]["pullbacks"], expected["pullbacks"])

    def test_deterministic_package_and_explanation(self):
        c, r = derive(self.source, self.selection)
        self.assertEqual(c, self.cert)
        self.assertEqual(r, self.result)
        self.assertEqual(explain(self.source, self.selection, c), explain(self.source, self.selection, self.cert))

    def test_independent_oracle_on_expression_family(self):
        expressions = ("true", "false", "x > 0", "x < 0", "x >= 0", "x <= 0", "x == 0", "x != 0",
                       "(x + 3) < 0", "(-x) >= 0", "(~x) <= 0", "x == 16", "x == 256",
                       "(x & (x - 1)) == 0", "(x > 0) ^ (x < 0)", "x > 0 && (x & (x - 1)) == 0")
        for typ in ("int", "long"):
            for expr in expressions:
                with self.subTest(typ=typ, expression=expr):
                    self.oracle(source(expr, typ), request(ENTRY, typ))

    def test_exhaustive_source_ir_and_factor(self):
        for expr in ("x>0", "x<=0", "x==16", "x==256", "true", "false", "(x & (x-1)) == 0"):
            for typ in ("int", "long"):
                s, r = source(expr, typ), request(ENTRY, typ)
                c, _ = derive(s, r)
                ir, m, _ = rebuild(s, r, c)
                for width in range(1, 9):
                    for x in range(1 << width):
                        self.assertEqual(factor_value(m, c["observations"], x, width), evaluate(ir, x, width))

    def test_delayed_source_requires_more_than_two_bits(self):
        s = source("x == 256")
        c, result, m = self.oracle(s, self.selection)
        self.assertEqual((result["model_states"], result["classes"]), (19, 11))
        proof = c["observations"]
        longest = max(proof["separators"], key=lambda row: len(row["word"]))
        left, right = [proof["blocks"][longest[k]][0] for k in ("left", "right")]
        shortest = shortest_terminal_separator(m, left, right)
        self.assertEqual(len(shortest), 8)
        for length in range(3):
            for word in itertools.product(m.alphabet, repeat=length):
                self.assertEqual(m.terminal[m.run(left, word)[1]], m.terminal[m.run(right, word)[1]])
        self.assertGreater(result["max_witness_length"], 2)

    def test_generated_expressions_against_oracle(self):
        rng = random.Random(29001)
        for _ in range(24):
            constant = rng.randrange(1, 32)
            op = rng.choice(("+", "-", "^", "&", "|"))
            relation = rng.choice(("==", "!=", ">", "<=", "<", ">="))
            self.oracle(source(f"(x {op} {constant}) {relation} 0"), self.selection)

    def test_state_renamings_generic_oracle(self):
        original = Model(self.cert["source_model"]["model"])
        expected = inequivalent_pairs(original)
        rng = random.Random(29002)
        for _ in range(12):
            names = list(original.states)
            rng.shuffle(names)
            rename = {s: "renamed_" + names[i] for i, s in enumerate(original.states)}
            d = deepcopy(original.data)
            d["states"] = list(rename.values())
            d["initial"] = rename[d["initial"]]
            d["terminal"] = {rename[s]: label for s, label in d["terminal"].items()}
            for cell in d["steps"]:
                cell["state"], cell["next"] = rename[cell["state"]], rename[cell["next"]]
            p = synthesize(d, row_encoding="atomic")["certificate"]
            check_generic(d, p)
            groups = {s: i for i, block in enumerate(p["blocks"]) for s in block}
            for s in original.states:
                for t in original.states:
                    self.assertEqual(groups[rename[s]] != groups[rename[t]], (s, t) in expected)

    def test_source_name_does_not_select_observations(self):
        # Rename the parameter with a lexical whole-word substitution.
        import re
        s = re.sub(r"\bx\b", "value", self.source.replace("Demo", "Else").replace(" f(", " calculate("))
        r = request({"class": "Else", "method": "calculate"}, "long")
        c, _ = derive(s, r)
        for field in ("predicates", "blocks", "cells", "rows", "separators"):
            self.assertEqual(c["observations"][field], self.cert["observations"][field])
        self.assertNotEqual(c["binding"], self.cert["binding"])

    def test_equivalent_sources_have_same_behavior_not_same_binding(self):
        s = source("x > 0 && ((x & (~x + 1)) == x)")
        c, result, m = self.oracle(s, self.selection)
        ir, _, _ = rebuild(self.source, self.selection, self.cert)
        self.assertEqual(result["classes"], self.result["classes"])
        for width in range(1, 8):
            for x in range(1 << width):
                self.assertEqual(factor_value(m, c["observations"], x, width), evaluate(ir, x, width))
        self.assertNotEqual(c["binding"]["source_sha256"], self.cert["binding"]["source_sha256"])

    def test_constant_keeps_empty_class(self):
        for expr in ("true", "false"):
            c, result, m = self.oracle(source(expr), self.selection)
            self.assertEqual((result["classes"], result["positive_classes"]), (2, 1))
            p = c["observations"]
            self.assertEqual(p["blocks"][p["initial"]], [m.initial])
            self.assertEqual(m.terminal[m.initial], EMPTY)

    def test_sign_is_final_not_first(self):
        c, _, m = self.oracle(source("x < 0"), self.selection)
        for word, label in (([], EMPTY), (["1"], "true"), (["1", "0"], "false")):
            result = replay(m.data, c["observations"], word)
            self.assertEqual(result["terminal"], label)
            self.assertTrue(all(y == "_" for y in result["outputs"]))

    def test_large_width_specializations(self):
        ir, m, _ = rebuild(self.source, self.selection, self.cert)
        for width in (1, 31, 32, 63, 64, 65, 128, 512, 4096):
            for x in (0, 1, (1 << width) - 1, 1 << (width - 1), (1 << (width - 1)) - 1):
                self.assertEqual(factor_value(m, self.cert["observations"], x, width), evaluate(ir, x, width))

    def test_source_and_request_substitution(self):
        with self.assertRaises(ValueError):
            check(self.source + "\n", self.selection, self.cert)
        c = deepcopy(self.cert)
        c["binding"]["request_sha256"] = digest({})
        self.reject(c)
        with self.assertRaises((ValueError, Unsupported)):
            check(self.source, request(ENTRY, "int"), self.cert)

    def test_no_target_partition_or_question_input(self):
        for extra in ("goal", "target", "questions", "partition"):
            with self.assertRaises(ValueError):
                derive(self.source, {**self.selection, extra: []})
        with self.assertRaises(TypeError):
            derive(self.source, self.selection, max_lookahead=8)

    def test_observation_proof_from_other_valid_source(self):
        c = deepcopy(self.cert)
        other, _ = derive(source("x > 0"), self.selection)
        c["observations"] = other["observations"]
        self.reject(c)

    def test_valid_forged_generic_table_rejected_at_source_bridge(self):
        c = deepcopy(self.cert)
        d = c["source_model"]["model"]
        key = next(s for s, label in d["terminal"].items() if label == "true")
        d["terminal"][key] = "false"
        forged = Model(d)
        p = synthesize(d, row_encoding="atomic")["certificate"]
        self.assertEqual(check_generic(d, p)["status"], "certified")
        c["observations"] = p
        c["binding"] = binding(self.selection, c["source_model"], forged)
        self.reject(c)

    def test_envelope_fields_schema_and_rehash(self):
        for field in ("schema", "binding", "source_model", "observations"):
            c = deepcopy(self.cert)
            c.pop(field)
            self.reject(c)
        c = {**deepcopy(self.cert), "target_checked": True}
        self.reject(c)
        c["schema"] = "qkf-unified-proof-v2"
        self.reject(c)

    def test_question_mask_and_label_corruption(self):
        for field, value in (("mask", 0), ("mask", True), ("label", "true")):
            c = deepcopy(self.cert)
            c["observations"]["predicates"][0][field] = value
            self.reject(c)

    def test_pullback_cycle_and_order_corruption(self):
        c, _ = derive(source("x == 256"), self.selection)
        for key, value in (("parent", 9), ("parent", True), ("symbol", "2")):
            changed = deepcopy(c)
            changed["observations"]["predicates"][2][key] = value
            with self.assertRaises(ValueError):
                check(source("x == 256"), self.selection, changed)

    def test_missing_or_duplicate_classes_and_source_states(self):
        for section, field in (("observations", "blocks"), ("source_model", "carrier")):
            c = deepcopy(self.cert)
            c[section][field].pop()
            self.reject(c)
            c = deepcopy(self.cert)
            c[section][field].append(deepcopy(c[section][field][-1]))
            self.reject(c)

    def test_atomic_row_and_consumer_cell_corruption(self):
        c = deepcopy(self.cert)
        c["observations"]["rows"][0]["supplied"][0][1] ^= 1
        self.reject(c)
        c = deepcopy(self.cert)
        c["observations"]["cells"][0]["next"] = 0
        self.reject(c)
        c = deepcopy(self.cert)
        c["observations"]["rows"][0]["kernel_projection"] ^= 1
        self.reject(c)

    def test_separator_coverage_and_wrong_witness(self):
        c = deepcopy(self.cert)
        c["observations"]["separators"].pop()
        self.reject(c)
        c = deepcopy(self.cert)
        c["observations"]["separators"][0]["left_value"] = "made-up"
        self.reject(c)

    def test_explain_checked_origins_and_reachable_prefixes(self):
        report = explain(self.source, self.selection, self.cert)
        _, m, _ = rebuild(self.source, self.selection, self.cert)
        for block in report["classes"]:
            for state, word in block["reachability_prefixes_lsb"].items():
                self.assertEqual(m.run(m.initial, word)[1], state)
        for q in report["questions"]:
            for state in m.states:
                _, end = m.run(state, q["word_lsb"])
                self.assertEqual(m.terminal[end] == q["label"], bool(q["mask"] & (1 << m.index[state])))
        self.assertFalse(report["target_checked"])

    def test_explain_rejects_corrupt_certificate(self):
        c = deepcopy(self.cert)
        c["observations"]["predicates"][0]["mask"] = 0
        with self.assertRaises(ValueError):
            explain(self.source, self.selection, c)

    def test_explicit_source_and_closure_budget_failures(self):
        for kwargs, stage in (({"max_states": 1}, "source_model"),
                              ({"max_observations": 0}, "observation_closure"),
                              ({"max_pullbacks": 0}, "observation_closure"),
                              ({"max_classes": 1}, "observation_closure")):
            c, r = derive(self.source, self.selection, **kwargs)
            self.assertIsNone(c)
            self.assertEqual((r["status"], r["stage"]), ("budget_exhausted", stage))
            self.assertFalse(r["target_checked"])

    def test_invalid_budget_types(self):
        for key, value in (("max_states", 65), ("max_states", True), ("max_classes", 0),
                           ("max_observations", -1), ("max_pullbacks", 100001)):
            with self.assertRaises(ValueError):
                derive(self.source, self.selection, **{key: value})

    def test_exact_sixty_four_state_boundary(self):
        s = source("4611686018427387904L == 0L")
        c, r = derive(s, self.selection)
        self.assertEqual((r["model_states"], r["classes"]), (64, 64))
        self.assertEqual(check(s, self.selection, c)["classes"], 64)
        self.assertIsNone(derive(s, self.selection, max_states=63)[0])

    def test_complete_atomic_generic_agreement_small_case(self):
        d = self.cert["source_model"]["model"]
        dense = synthesize(d, row_encoding="complete")["certificate"]
        check_generic(d, dense)
        for field in ("predicates", "blocks", "initial", "cells", "separators"):
            self.assertEqual(dense[field], self.cert["observations"][field])
        c = deepcopy(self.cert)
        c["observations"] = dense
        self.reject(c)  # this new route deliberately has one encoding

    def test_unsupported_source_is_not_refutation(self):
        with self.assertRaises(Unsupported):
            derive(source("(x >> 1) == 0"), self.selection)

    def call_cli(self, root, command, *extra):
        args = [command, str(root / "input.java"), "--class", "Demo", "--method", "f",
                "--word-type", "long", "--certificate", str(root / "proof.json"), *extra]
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(args)
        return code, json.loads(output.getvalue())

    def test_cli_roundtrip_explain_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "input.java").write_text(self.source)
            self.assertEqual(self.call_cli(root, "infer")[0], 0)
            raw = (root / "proof.json").read_bytes()
            self.assertEqual(self.call_cli(root, "check")[0], 0)
            self.assertEqual(self.call_cli(root, "explain")[0], 0)
            self.assertEqual(self.call_cli(root, "infer")[0], 64)
            self.assertEqual(raw, (root / "proof.json").read_bytes())

    def test_cli_budget_produces_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "input.java").write_text(self.source)
            code, r = self.call_cli(root, "infer", "--max-observations", "0")
            self.assertEqual((code, r["status"]), (2, "budget_exhausted"))
            self.assertFalse((root / "proof.json").exists())

    def test_cli_hostile_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "input.java").write_text(self.source)
            for raw in ('{"schema":1,"schema":2}', '{"value":NaN}', '{', '[]'):
                (root / "proof.json").write_text(raw)
                code, r = self.call_cli(root, "check")
                self.assertEqual((code, r["status"]), (3, "invalid_certificate"))

    def test_old_bridge_and_v3_remain_checkable(self):
        from research.signed_bridge.checker import check as old_check
        self.assertEqual(old_check(self.source, self.selection, self.cert["source_model"])["status"], "source_model_verified")
        from research.inference.v3_producer import infer
        from research.inference.v3_checker import check as v3_check
        target = {"schema": "qkf-target-v2", "kind": "signed_boolean_predicate",
                  "source": {"entry": ENTRY, "word_type": "long"},
                  "goal": ["and", ["positive"], ["popcount_eq", 1]]}
        certificate, _ = infer(self.source, target)
        self.assertEqual(v3_check(self.source, target, certificate)["status"], "certified")

    def test_guarded_fresh_process_normal_and_optimized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.java").write_text(self.source)
            (root / "certificate.json").write_text(json.dumps(self.cert))
            (root / "request.json").write_text(json.dumps(self.selection))
            script = r'''
import builtins, json, sys
from pathlib import Path
original = builtins.__import__
def guard(name, *a, **kw):
    if 'producer' in name or name.split('.')[0] in {'subprocess','z3','pysmt','cvc5'}:
        raise RuntimeError('forbidden import: '+name)
    return original(name, *a, **kw)
builtins.__import__ = guard
from research.signed_observations.checker import check
from research.signed_observations.explain import explain
p=Path(sys.argv[1]); s=(p/'source.java').read_text()
r=json.loads((p/'request.json').read_text()); c=json.loads((p/'certificate.json').read_text())
v=check(s,r,c); e=explain(s,r,c)
if v['status'] != 'source_observation_verified' or v['target_checked'] or len(e['classes']) != v['classes']:
    raise RuntimeError('scope mismatch')
print('checked')
'''
            for flags in ([], ["-O"]):
                run = subprocess.run([sys.executable, *flags, "-c", script, str(root)], cwd=ROOT,
                                     capture_output=True, text=True, check=False)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                self.assertEqual(run.stdout.strip(), "checked")


if __name__ == "__main__":
    unittest.main()
