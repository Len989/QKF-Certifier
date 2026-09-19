"""Source correspondence, hostile-certificate, completion and compatibility tests."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from research.observations.model import Model, digest
from research.signed_predicates.semantics import evaluate
from research.wordexpr.frontend import Unsupported
from .checker import check, check_observations, rebuild
from .cli import load, main
from .model import EMPTY, CapacityExceeded, request, word_value
from .producer import derive

ROOT = Path(__file__).resolve().parents[2]
ENTRY = {"class": "Demo", "method": "f"}


def source(expression="x > 0 && (x & (x - 1)) == 0", word_type="long"):
    return "class Demo { public static boolean f(" + word_type + " x) { return " + expression + "; } }"


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.source, self.selection = source(), request(ENTRY, "long")
        self.cert, self.result = derive(self.source, self.selection)

    def reject(self, cert):
        with self.assertRaises(ValueError):
            check(self.source, self.selection, cert)

    def test_roundtrip_and_scope(self):
        self.assertEqual(check(self.source, self.selection, self.cert), self.result)
        self.assertEqual(self.result["status"], "source_model_verified")
        self.assertFalse(self.result["target_checked"])
        self.assertFalse(self.result["lean_checked"])
        self.assertTrue(self.result["all_positive_widths_in_declared_profile"])
        self.assertEqual(self.result["checked_edges"], 2 * self.result["model_states"])

    def test_deterministic_certificate(self):
        other, result = derive(self.source, self.selection)
        self.assertEqual(digest(other), digest(self.cert))
        self.assertEqual(result, self.result)

    def test_exhaustive_small_widths(self):
        expressions = ("x > 0", "x >= 0", "x < 0", "x <= 0", "0 < x", "0 >= x",
                       "x == 0", "x != 0", "(-x) >= 0", "(x + 3) < 0",
                       "(~x) <= 0", "x > 0 && (x & (x - 1)) == 0",
                       "(x > 0) ^ (x < 0)", "x > 0 & (x & (x - 1)) == 0", "true", "false")
        for word_type in ("int", "long"):
            for expression in expressions:
                s, r = source(expression, word_type), request(ENTRY, word_type)
                cert, _ = derive(s, r)
                ir, model = rebuild(s, r, cert)
                for width in range(1, 8):
                    for x in range(1 << width):
                        self.assertEqual(word_value(model, x, width), evaluate(ir, x, width),
                                         (expression, word_type, width, x))

    def test_large_width_boundaries(self):
        ir, model = rebuild(self.source, self.selection, self.cert)
        for width in (1, 2, 31, 32, 63, 64, 65, 127, 512, 4096):
            for x in (0, 1, (1 << width) - 1, 1 << (width - 1), (1 << (width - 1)) - 1):
                self.assertEqual(word_value(model, x, width), evaluate(ir, x, width))

    def test_no_zero_width_value(self):
        _, model = rebuild(self.source, self.selection, self.cert)
        self.assertEqual(model.terminal[model.initial], EMPTY)
        for x, width in ((0, 0), (0, -1), (0, True), (False, 1), (-1, 2), (4, 2)):
            with self.assertRaises(ValueError):
                word_value(model, x, width)

    def test_initial_residual_reachable_at_positive_width(self):
        s, r = source("x < 0"), request(ENTRY, "long")
        cert, _ = derive(s, r)
        _, model = rebuild(s, r, cert)
        root = cert["carrier"][0]["residual"]
        self.assertTrue(any(row["has_bits"] and row["residual"] == root for row in cert["carrier"]))
        _, after_zero = model.step[model.initial, "0"]
        self.assertNotEqual(after_zero, model.initial)
        self.assertEqual(model.terminal[after_zero], "false")

    def test_constant_results_still_distinguish_no_word(self):
        for expr in ("true", "false"):
            s = source(expr)
            cert, result = derive(s, self.selection)
            self.assertEqual(result["model_states"], 2)
            self.assertEqual(result["distinct_residual_vectors"], 1)
            self.assertEqual(cert["model"]["terminal"], {"q000": EMPTY, "q001": expr})

    def test_sign_only_at_final_bit(self):
        s = source("x < 0")
        c, _ = derive(s, self.selection)
        _, m = rebuild(s, self.selection, c)
        _, first = m.run(m.initial, ["1"])
        _, second = m.run(m.initial, ["1", "0"])
        self.assertEqual(m.terminal[first], "true")
        self.assertEqual(m.terminal[second], "false")
        self.assertTrue(all(row["output"] == "_" for row in c["model"]["steps"]))

    def test_source_bytes_binding(self):
        with self.assertRaises(ValueError):
            check(self.source + "\n", self.selection, self.cert)

    def test_request_type_and_entry_binding(self):
        for key, value in (("word_type", "int"), ("entry", {"class": "Demo", "method": "g"}),
                           ("contract", "other"), ("schema", "other")):
            selection = deepcopy(self.selection)
            selection[key] = value
            with self.assertRaises((ValueError, Unsupported)):
                check(self.source, selection, self.cert)

    def test_target_field_cannot_be_smuggled(self):
        r = {**self.selection, "target": ["positive"]}
        with self.assertRaises(ValueError):
            derive(self.source, r)

    def test_overloads_and_unused_other_method(self):
        s = "class Demo { public static boolean f(int x){return x<0;} public static boolean f(long x){return x>=0;} }"
        for typ, answer in (("int", False), ("long", True)):
            r = request(ENTRY, typ)
            c, _ = derive(s, r)
            _, m = rebuild(s, r, c)
            self.assertEqual(word_value(m, 0, 32), answer)

    def test_annotation_and_locals(self):
        s = 'class Demo { @SuppressWarnings("unused") public static boolean f(long x){ final long y=x-1; boolean b=x>0; return b & (x & y)==0; } }'
        c, _ = derive(s, self.selection)
        ir, m = rebuild(s, self.selection, c)
        for x in range(256):
            self.assertEqual(word_value(m, x, 8), evaluate(ir, x, 8))

    def test_names_do_not_choose_transitions(self):
        renamed = self.source.replace("Demo", "Other").replace(" f(", " anything(")
        r = request({"class": "Other", "method": "anything"}, "long")
        c, _ = derive(renamed, r)
        for field in ("steps", "terminal", "initial", "states"):
            self.assertEqual(c["model"][field], self.cert["model"][field])

    def test_ir_mutation_rejected(self):
        c = deepcopy(self.cert)
        c["ir"]["formula"] = ["literal", True]
        c["binding"]["source_ir_sha256"] = digest(c["ir"])
        self.reject(c)

    def test_every_model_surface_rejected_even_when_rehashed(self):
        for field in ("terminal", "steps", "initial", "alphabet", "outputs", "binding", "states"):
            c = deepcopy(self.cert)
            if field == "terminal":
                c["model"][field]["q000"] = "false"
            elif field == "steps":
                c["model"][field][0]["next"] = "q000"
            elif field == "initial":
                c["model"][field] = "q001"
            elif field in ("alphabet", "outputs", "states"):
                c["model"][field].pop()
            else:
                c["model"][field]["completion"] = "width-zero-allowed"
            digest(c["model"])  # New hashes cannot make the semantics true.
            self.reject(c)

    def test_incomplete_reachable_carrier(self):
        c = deepcopy(self.cert)
        c["carrier"].pop()
        self.reject(c)

    def test_missing_or_duplicate_transition(self):
        for duplicate in (False, True):
            c = deepcopy(self.cert)
            c["model"]["steps"].pop()
            if duplicate:
                c["model"]["steps"].append(c["model"]["steps"][0])
            self.reject(c)

    def test_duplicate_source_state(self):
        c = deepcopy(self.cert)
        c["carrier"].append(deepcopy(c["carrier"][-1]))
        self.reject(c)

    def test_invalid_parent_types_cycle_and_symbol(self):
        for parent in ([True, "0"], [999, "0"], [1, "0"], [0, 0], [0, "2"], None):
            c = deepcopy(self.cert)
            c["carrier"][1]["parent"] = parent
            self.reject(c)

    def test_forged_completion_flags(self):
        for i, flag in ((0, True), (1, False), (1, 1)):
            c = deepcopy(self.cert)
            c["carrier"][i]["has_bits"] = flag
            self.reject(c)

    def test_residual_types_and_unreachable_state(self):
        for value in (True, 999, -999):
            c = deepcopy(self.cert)
            c["carrier"][1]["residual"][0] = value
            self.reject(c)
        c = deepcopy(self.cert)
        # A well-typed vector, but not the stated source successor.
        c["carrier"][1]["residual"] = list(c["carrier"][2]["residual"])
        self.reject(c)

    def test_model_budget_exact_boundary_and_exhaustion(self):
        s = source("4611686018427387904L == 0L")
        c, r = derive(s, self.selection)
        self.assertEqual(r["model_states"], 64)
        self.assertEqual(check(s, self.selection, c), r)
        with self.assertRaises(CapacityExceeded):
            derive(s, self.selection, max_states=63)
        with self.assertRaises(CapacityExceeded):
            derive(source("x == 9223372036854775807L"), self.selection)
        for bound in (0, 65, True):
            with self.assertRaises(ValueError):
                derive(self.source, self.selection, max_states=bound)

    def test_random_expressions_small_words(self):
        rng = random.Random(28001)
        for _ in range(20):
            k = rng.randrange(1, 16)
            expression = "((x " + rng.choice(("+", "-", "&", "|", "^")) + " " + str(k) + ") < 0) ^ (x == 0)"
            s = source(expression)
            c, _ = derive(s, self.selection)
            ir, m = rebuild(s, self.selection, c)
            for x in range(64):
                self.assertEqual(word_value(m, x, 6), evaluate(ir, x, 6))

    def test_unsupported_grammar(self):
        for expression in ("x >> 1 == 0", "Math.abs(x) > 0", "x < (x+1)", "(int)x == 0"):
            with self.assertRaises(Unsupported):
                derive(source(expression), self.selection)

    def test_existing_observation_checker_accepts_rebuilt_model(self):
        # Compatibility test only: the public PR28 producer does NOT derive
        # these observations. The integrated route is planned for PR29.
        from research.observations.producer import synthesize
        proposed = synthesize(self.cert["model"], row_encoding="atomic")
        self.assertEqual(proposed["status"], "candidate")
        result = check_observations(self.source, self.selection, self.cert, proposed["certificate"])
        self.assertEqual(result["status"], "source_observation_verified")
        self.assertFalse(result["target_checked"])
        self.assertIn("not a target", result["scope"])

    def test_forged_model_with_valid_generic_proof_rejected(self):
        from research.observations.producer import synthesize
        forged = deepcopy(self.cert)
        forged["model"]["terminal"] = {s: "true" for s in forged["model"]["states"]}
        # This proof really is valid for the substituted generic table.
        proposed = synthesize(forged["model"], row_encoding="atomic")["certificate"]
        from research.observations.checker import check as finite_check
        self.assertEqual(finite_check(forged["model"], proposed)["status"], "certified")
        with self.assertRaises(ValueError):
            check_observations(self.source, self.selection, forged, proposed)

    def test_observation_proof_of_other_source_rejected(self):
        from research.observations.producer import synthesize
        other, _ = derive(source("false"), self.selection)
        proof = synthesize(other["model"], row_encoding="atomic")["certificate"]
        with self.assertRaises(ValueError):
            check_observations(self.source, self.selection, self.cert, proof)

    def test_existing_signed_and_inference_certificates_unchanged(self):
        from research.inference.test_inference_v3 import target
        from research.inference.v3_producer import infer
        from research.inference.v3_checker import check as check_v3
        from research.signed_predicates.experiment import specification
        from research.signed_predicates.producer import derive as derive_v1
        from research.signed_predicates.checker import check as check_v1
        old, result = infer(self.source, target("long"))
        self.assertEqual(check_v3(self.source, target("long"), old), result)
        spec = specification(ENTRY, "long")
        old, result = derive_v1(self.source, spec)
        self.assertEqual(check_v1(self.source, spec, old), result)

    def test_fresh_replay_no_producers_native_or_smt(self):
        from research.observations.producer import synthesize
        obs = synthesize(self.cert["model"], row_encoding="atomic")["certificate"]
        payload = json.dumps([self.source, self.selection, self.cert, obs])
        script = '''
import builtins, json, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if 'producer' in name or name.split('.')[0] in {'subprocess','z3','cvc5','pysmt'}:
        raise RuntimeError('forbidden bridge replay import: '+name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from research.signed_bridge.checker import check, check_observations
source, selection, cert, obs = json.load(sys.stdin)
if check(source, selection, cert)['status'] != 'source_model_verified':
    raise RuntimeError('bridge did not verify')
result = check_observations(source, selection, cert, obs)
if result['status'] != 'source_observation_verified':
    raise RuntimeError('not verified')
print(json.dumps(result))
'''
        for opt in ([], ["-O"]):
            child = subprocess.run([sys.executable, "-B", *opt, "-c", script], input=payload,
                                   text=True, capture_output=True, cwd=ROOT, timeout=30)
            self.assertEqual(child.returncode, 0, child.stderr)
            self.assertFalse(json.loads(child.stdout)["target_checked"])


class CliTests(unittest.TestCase):
    def test_build_check_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            src, cert = path / "Demo.java", path / "proof.json"
            src.write_text(source())
            tail = [str(src), "--class", "Demo", "--method", "f", "--word-type", "long", "--certificate", str(cert)]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["build", *tail]), 0)
                original = cert.read_bytes()
                self.assertEqual(main(["check", *tail]), 0)
                self.assertEqual(main(["build", *tail]), 64)
            self.assertEqual(cert.read_bytes(), original)

    def test_failed_build_never_writes_certificate(self):
        for expression, extra in (("x >> 1 == 0", []), ("x < 0", ["--max-states", "1"])):
            with tempfile.TemporaryDirectory() as temp:
                src, cert = Path(temp) / "Demo.java", Path(temp) / "proof.json"
                src.write_text(source(expression))
                with redirect_stdout(io.StringIO()):
                    code = main(["build", str(src), "--class", "Demo", "--method", "f", "--word-type", "long",
                                 "--certificate", str(cert), *extra])
                self.assertEqual(code, 2)
                self.assertFalse(cert.exists())

    def test_strict_json(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "bad.json"
            for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
                p.write_text(raw)
                with self.assertRaises(ValueError):
                    load(p)

    def test_invalid_certificate_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            src, cert = Path(temp) / "Demo.java", Path(temp) / "proof.json"
            src.write_text(source())
            cert.write_text('{}')
            with redirect_stdout(io.StringIO()):
                code = main(["check", str(src), "--class", "Demo", "--method", "f", "--word-type", "long",
                             "--certificate", str(cert)])
            self.assertEqual(code, 3)


if __name__ == "__main__":
    unittest.main()
