"""Local laws, source projection, hostile proofs and pre-enumeration savings."""
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
from unittest.mock import patch

from research.observations.model import digest
from research.signed_bridge.model import CapacityExceeded, request, word_value
from research.signed_predicates import semantics
from research.wordexpr.frontend import Unsupported
from . import bridge, checker, cli, rules
from .producer import ReductionLimit, derive

ENTRY = {"class": "Demo", "method": "f"}
ROOT = Path(__file__).resolve().parents[2]


def source(expression, typ="long", pre=""):
    return f"class Demo {{ public static boolean f({typ} x) {{ {pre}return {expression}; }} }}"


def boolean(term, values):
    """Independent propositional oracle, not the signed formula interpreter."""
    if term[0] == "literal":
        return term[1]
    if term[0] == "atom":
        return values[term[1]]
    if term[0] == "not":
        return not boolean(term[1], values)
    a, b = boolean(term[1], values), boolean(term[2], values)
    return {"and": a and b, "or": a or b, "xor": a != b}[term[0]]


class ReductionTests(unittest.TestCase):
    def setUp(self):
        self.selection = request(ENTRY, "long")
        self.text = source("x == 2147483648L || x != 2147483648L")
        self.cert, self.result = derive(self.text, self.selection)

    def reject(self, cert):
        with self.assertRaises((ValueError, KeyError, TypeError, IndexError)):
            checker.check(self.text, self.selection, cert)

    def test_roundtrip_scope(self):
        self.assertEqual(checker.check(self.text, self.selection, self.cert), self.result)
        self.assertEqual(self.result["status"], "source_reduction_verified")
        self.assertEqual(self.result["original_states_enumerated"], 0)
        self.assertFalse(self.result["target_checked"])
        self.assertFalse(self.result["lean_checked"])

    def test_determinism(self):
        self.assertEqual((self.cert, self.result), derive(self.text, self.selection))

    def test_all_rule_identifiers_have_actual_source_witnesses(self):
        examples = ("(x == 1) || !(1 == x)", "x == x", "0 >= 0", "!true", "!!(x > 0)",
                    "false || x > 0", "(x > 0) ^ (x > 0)", "(x < 0) && !(x < 0)",
                    "(x > 0) || ((x > 0) && x == 1)")
        used = set()
        for e in examples:
            cert, _ = derive(source(e), self.selection)
            used.update(step["rule"] for step in cert["steps"])
        self.assertEqual(used, set(rules.RULES))

    def test_boolean_laws_exhaustive_independent_truth_tables(self):
        leaves = [["literal", False], ["literal", True], ["atom", 0], ["atom", 1]]
        terms = leaves + [["not", x] for x in leaves]
        terms += [[op, x, y] for op in ("and", "or", "xor") for x in terms[:] for y in terms[:]]
        terms += [[op, x, [dual, y, x]] for op, dual in (("and", "or"), ("or", "and"))
                  for x in leaves for y in leaves]
        ir = {"atoms": [{"kind": "signed_zero", "node": 0, "op": ">"},
                        {"kind": "signed_zero", "node": 0, "op": "<"}], "nodes": [["input"]]}
        checked = 0
        for t in terms + [["not", t] for t in terms]:
            for rule in rules.RULES[3:]:
                new = rules.rhs(ir, t, rule)
                if new is not None:
                    for values in itertools.product((False, True), repeat=2):
                        self.assertEqual(boolean(t, values), boolean(new, values), (rule, t))
                        checked += 1
        self.assertGreater(checked, 500)

    def test_atomic_alias_symmetry_without_independence_assumption(self):
        s = source("(x == 1) || !(1 == x)")
        c, _ = derive(s, self.selection)
        self.assertEqual(c["reduced_ir"]["atoms"], [])
        self.assertEqual(c["final_formula"], ["literal", True])
        self.assertIn("atom-alias", [r["rule"] for r in c["steps"]])

    def test_frontend_already_shares_identical_atoms(self):
        c, _ = derive(source("(x == 1) || (x == 1)"), self.selection)
        self.assertEqual(len(c["original_ir"]["atoms"]), 1)
        self.assertEqual(len(c["reduced_ir"]["atoms"]), 1)

    def test_signed_literal_is_not_constant_folded_across_widths(self):
        c, _ = derive(source("2147483648L > 0"), self.selection)
        self.assertEqual(c["steps"], [])
        _, reduced = checker.rebuild(source("2147483648L > 0"), self.selection, c)
        self.assertFalse(semantics.evaluate(reduced, 0, 32))
        self.assertTrue(semantics.evaluate(reduced, 0, 33))

    def test_no_arithmetic_word_rewrite_is_smuggled(self):
        c, _ = derive(source("(x - x) == 0"), self.selection)
        self.assertEqual(c["steps"], [])
        self.assertTrue(any(row[0] == "sub" for row in c["reduced_ir"]["nodes"]))

    def test_dead_locals_and_assignments_project_actual_return(self):
        s = source("b", pre="long unused = x + 2147483648L; boolean b=x<0; b=true; ")
        c, r = derive(s, self.selection)
        self.assertGreater(r["word_nodes_before"], 1)
        self.assertEqual(c["reduced_ir"]["nodes"], [["input"]])
        self.assertEqual(c["projection"]["atoms"], [])

    def test_dead_unsupported_operation_still_rejected(self):
        for pre in ("long unused=x>>1; ", "long unused=unknown(x); ", "long unused=x/0; "):
            with self.assertRaises(Unsupported):
                derive(source("true", pre=pre), self.selection)

    def test_source_target_fields_forbidden(self):
        with self.assertRaises(ValueError):
            derive(self.text, {**self.selection, "target": ["positive"]})
        with self.assertRaises(TypeError):
            derive(self.text, self.selection, target=["positive"])

    def test_source_and_overload_binding(self):
        for s, r in ((self.text + "\n", self.selection),
                     (self.text.replace("||", "&&"), self.selection),
                     (self.text, request(ENTRY, "int"))):
            with self.assertRaises(ValueError):
                checker.check(s, r, self.cert)

    def test_certificate_field_types_and_missing_dependencies(self):
        for field in self.cert:
            c = deepcopy(self.cert)
            del c[field]
            self.reject(c)
        for key, value in (("schema", "old"), ("steps", {}), ("final_formula", ["literal", 1])):
            c = deepcopy(self.cert); c[key] = value; self.reject(c)

    def test_rehashed_original_ir_does_not_bypass_reparse(self):
        c = deepcopy(self.cert)
        c["original_ir"]["formula"] = ["literal", False]
        c["binding"]["original_ir_sha256"] = digest(c["original_ir"])
        self.reject(c)

    def test_false_reduced_ir_even_with_matching_fake_projection(self):
        c = deepcopy(self.cert)
        c["reduced_ir"]["formula"] = ["literal", False]
        self.reject(c)
        c["final_formula"] = ["literal", False]
        self.reject(c)

    def test_missing_and_wrong_rewrite_steps(self):
        c = deepcopy(self.cert); c["steps"] = []; self.reject(c)
        for rule in ("idempotent", "arbitrary-assumption", 0):
            c = deepcopy(self.cert); c["steps"][0]["rule"] = rule; self.reject(c)

    def test_paths_cannot_select_payload_or_cycle(self):
        for path in ([False], [0], [1, 1], [99], "", [1]*32):
            c = deepcopy(self.cert); c["steps"][0]["path"] = path; self.reject(c)

    def test_projection_cannot_drop_live_or_keep_unjustified_data(self):
        for projection in ({"nodes": [], "atoms": []}, {"nodes": [False], "atoms": []},
                           {"nodes": [0, 1], "atoms": []}, {"nodes": [0], "atoms": [0]}):
            c = deepcopy(self.cert); c["projection"] = projection; self.reject(c)
        s = source("(x+3)<0"); c, _ = derive(s, self.selection)
        c["reduced_ir"]["nodes"][2][1] = 2  # forged self-reference
        with self.assertRaises(ValueError): checker.check(s, self.selection, c)

    def test_valid_nonmaximal_trace_is_equivalence_not_normal_form(self):
        c = deepcopy(self.cert)
        c["steps"] = []; c["final_formula"] = c["original_ir"]["formula"]
        c["reduced_ir"], c["projection"] = rules.compact(c["original_ir"], c["final_formula"])
        self.assertEqual(checker.check(self.text, self.selection, c)["status"], "source_reduction_verified")

    def test_zero_step_budget_and_trace_ceiling(self):
        with self.assertRaises(ReductionLimit): derive(self.text, self.selection, max_steps=0)
        self.assertEqual(derive(source("x<0"), self.selection, max_steps=0)[0]["steps"], [])
        for budget in (-1, True, 513):
            with self.assertRaises(ValueError): derive(self.text, self.selection, max_steps=budget)
        c = deepcopy(self.cert); c["steps"] *= 513; self.reject(c)

    def test_formula_typing_guards(self):
        bad = (["literal", 0], ["atom", True], ["atom", 3], ["word", 0], ["not"], [],
               ["and", ["literal", True], ["atom", -1]])
        for term in bad:
            with self.assertRaises(ValueError): rules.validate_formula(term, 2)

    def test_exhaustive_source_reduced_and_model_small_words(self):
        expressions = ("x > 0", "false", "true", "x == x", "0 <= 0", "!true",
            "!!(x < 0)", "false || (x >= 0)", "(x > 0) ^ true", "(x < 0) ^ (x < 0)",
            "(x == 16) || !(x == 16)", "(x < 0) && !(x < 0)",
            "(x > 0) || ((x > 0) && x == 16)", "(x == 1) | !(1 == x)",
            "(x+3)<0 && true", "(x & (x-1)) == 0 && x>0")
        for typ, expression in itertools.product(("int", "long"), expressions):
            s, selection = source(expression, typ), request(ENTRY, typ)
            c, _ = bridge.build(s, selection)
            original, reduced, model = bridge.rebuild_model(s, selection, c)
            for width in range(1, 8):
                for x in range(1 << width):
                    self.assertEqual(semantics.evaluate(original, x, width), semantics.evaluate(reduced, x, width))
                    self.assertEqual(semantics.evaluate(original, x, width), word_value(model, x, width))

    def test_generated_boolean_contexts(self):
        rng = random.Random(33001)
        atoms = ("x==16", "x<0", "(x & (x-1))==0")
        for _ in range(48):
            a, b = rng.choice(atoms), rng.choice(atoms)
            expression = rng.choice((f"({a}) || !({a})", f"({a}) && (({a}) || ({b}))",
                                     f"(!({a}) ^ true) || (({b}) && false)", f"!!({a}) ^ ({b})"))
            s = source(expression); c, _ = bridge.build(s, self.selection)
            original, _, model = bridge.rebuild_model(s, self.selection, c)
            for width in range(1, 7):
                for x in range(1 << width):
                    self.assertEqual(semantics.evaluate(original, x, width), word_value(model, x, width))

    def test_residual_dependency_projection_commutes(self):
        s = source("(x + 3) < 0", pre="long ignored=x+16; boolean unused=x==7; ")
        cert, _ = derive(s, self.selection)
        original, reduced = checker.rebuild(s, self.selection, cert)
        nm, am = cert["projection"]["nodes"], cert["projection"]["atoms"]
        def projection(state):
            n = len(original["nodes"])
            return tuple(state[i] for i in nm) + tuple(state[n+2*i+j] for i in am for j in (0,1))
        states, seen = [semantics.initial(original)], {semantics.initial(original)}
        self.assertEqual(projection(states[0]), semantics.initial(reduced))
        for state in states:
            for bit in ("0", "1"):
                nxt = semantics.cell(original, state, bit)
                self.assertEqual(projection(nxt), semantics.cell(reduced, projection(state), bit))
                if nxt not in seen: states.append(nxt); seen.add(nxt)

    def test_tautology_has_two_states_without_enumerating_original(self):
        with patch("research.signed_bridge.producer.derive", side_effect=AssertionError("old enumeration")):
            observed = []
            original_cell = semantics.cell
            def cell(ir, state, symbol):
                self.assertEqual(ir["nodes"], [["input"]]); self.assertEqual(ir["atoms"], [])
                observed.append(1)
                return original_cell(ir, state, symbol)
            with patch.object(semantics, "cell", side_effect=cell):
                c, result = bridge.infer(self.text, self.selection, max_states=2)
        self.assertTrue(observed)
        self.assertEqual((result["model_states"], result["classes"]), (2, 2))
        self.assertEqual(bridge.check_observations(self.text, self.selection, c), result)

    def test_actual_pr32_tautology_source_identity(self):
        s = "class Demo { public static boolean f(long x) { return x == 2147483648L || x != 2147483648L; } }"
        import hashlib
        registration = json.loads((ROOT / "research/acceptance/REGISTERED_CASES.json").read_text())
        row = next(r for r in registration if r["id"] == "tautology_31")
        self.assertEqual(hashlib.sha256(s.encode()).hexdigest(), row["source_sha256"])
        self.assertEqual(bridge.build(s, self.selection)[1]["model_states"], 2)

    def test_original_bridge_still_exhausts_same_case(self):
        from research.signed_bridge.producer import derive as old
        with self.assertRaises(CapacityExceeded): old(self.text, self.selection)

    def test_delayed_nontrivial_case_still_exhausts(self):
        c, result = bridge.infer(source("x == 2147483648L"), self.selection)
        self.assertIsNone(c); self.assertEqual(result["stage"], "reduced_source_model")

    def test_renamed_and_nested_family(self):
        for exponent in (4, 8, 30, 31, 62):
            s = source(f"!(!((x=={1<<exponent}L) || !(x=={1<<exponent}L)))")
            renamed = s.replace("Demo", "Renamed").replace(" f(", " other(").replace(" x", " value").replace("(x", "(value")
            r = request({"class": "Renamed", "method": "other"}, "long")
            for text, select in ((s, self.selection), (renamed, r)):
                c, result = bridge.build(text, select, max_states=2)
                self.assertEqual(result["model_states"], 2)
                self.assertNotEqual(c["model"]["terminal"]["q000"], "true")

    def test_damaged_reduced_carrier_and_model_rejected(self):
        certificate, _ = bridge.build(self.text, self.selection)
        mutations = (lambda c: c["carrier"].pop(),
                     lambda c: c["carrier"].append(deepcopy(c["carrier"][-1])),
                     lambda c: c["carrier"][1].update(parent=[1,"0"]),
                     lambda c: c["carrier"][1].update(has_bits=False),
                     lambda c: c["model"]["terminal"].update(q001="false"),
                     lambda c: c["binding"].update(completion="allow-empty"))
        for mutation in mutations:
            c = deepcopy(certificate); mutation(c)
            with self.assertRaises(ValueError): bridge.check_model(self.text, self.selection, c)

    def test_forged_generic_model_does_not_bypass_source_binding(self):
        from research.observations.model import Model
        from research.observations.producer import synthesize
        from research.observations.checker import check as generic
        c, _ = bridge.infer(self.text, self.selection)
        altered = deepcopy(c["source_model"]["model"])
        altered["terminal"]["q001"] = "false"
        forged = Model(altered)
        proof = synthesize(forged.data, row_encoding="atomic")["certificate"]
        self.assertEqual(generic(forged.data, proof)["status"], "certified")
        c["source_model"]["model"], c["observations"] = forged.data, proof
        with self.assertRaises(ValueError): bridge.check_observations(self.text, self.selection, c)

    def test_observation_tampering(self):
        c, _ = bridge.infer(source("x>0"), self.selection)
        for field in ("rows", "cells", "separators"):
            bad = deepcopy(c); bad["observations"][field].pop()
            with self.assertRaises(ValueError): bridge.check_observations(source("x>0"), self.selection, bad)

    def test_distinct_budget_stages_and_no_partial_proof(self):
        for kwargs, stage in (({"max_steps":0}, "source_reduction"),
                              ({"max_states":1}, "reduced_source_model"),
                              ({"max_observations":0}, "observation_closure"),
                              ({"max_classes":1}, "observation_closure")):
            c, result = bridge.infer(self.text, self.selection, **kwargs)
            self.assertIsNone(c); self.assertEqual(result["stage"], stage)

    def test_exact_model_budget_boundary(self):
        s = source("4611686018427387904L == 0L")
        self.assertEqual(bridge.build(s, self.selection)[1]["model_states"], 64)
        with self.assertRaises(CapacityExceeded): bridge.build(s, self.selection, max_states=63)
        for n in (0, True, 65):
            with self.assertRaises(ValueError): bridge.build(s, self.selection, max_states=n)

    def test_word_boundaries_and_empty_input(self):
        for e in ("(x<0) || ((x<0) && x==16)", "true", "x==x"):
            s = source(e); c, _ = bridge.build(s, self.selection)
            original, _, model = bridge.rebuild_model(s, self.selection, c)
            for w in (1,2,31,32,33,63,64,65,127,4096):
                for x in (0,1,(1<<w)-1,1<<(w-1)):
                    self.assertEqual(semantics.evaluate(original,x,w),word_value(model,x,w))
            with self.assertRaises(ValueError): word_value(model,0,0)

    def test_old_schemas_stay_old(self):
        from research.signed_bridge.producer import derive as old
        from research.signed_bridge.checker import check as old_check
        s = source("x<0"); old_c, result = old(s, self.selection)
        self.assertEqual(old_check(s, self.selection, old_c), result)
        new_c, _ = bridge.build(s, self.selection)
        with self.assertRaises(ValueError): old_check(s, self.selection, new_c)
        with self.assertRaises(ValueError): bridge.check_model(s, self.selection, old_c)

    def test_source_only_proof_not_accepted_as_target(self):
        from research.unified.v4 import check
        c, _ = bridge.infer(self.text, self.selection)
        target = {"schema":"qkf-target-v2","kind":"signed_boolean_predicate",
                  "source":{"entry":ENTRY,"word_type":"long"},"goal":["positive"]}
        with self.assertRaises(ValueError): check(self.text, target, c)

    def test_cli_infer_check_and_exclusive_write(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); (root/"source.java").write_text(self.text)
            common = [str(root/"source.java"),"--class","Demo","--method","f","--word-type","long",
                      "--certificate",str(root/"proof.json")]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["infer",*common]),0)
                self.assertEqual(cli.main(["check",*common]),0)
                self.assertEqual(cli.main(["infer",*common]),64)

    def test_cli_budget_leaves_no_certificate(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); (root/"s.java").write_text(self.text)
            with redirect_stdout(io.StringIO()):
                code = cli.main(["infer",str(root/"s.java"),"--class","Demo","--method","f","--word-type","long",
                                 "--certificate",str(root/"c.json"),"--max-states","1"])
            self.assertEqual(code,2); self.assertFalse((root/"c.json").exists())

    def test_strict_json_reused(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"c.json"
            for text in ('{"a":1,"a":2}', '{"x":NaN}'):
                p.write_text(text)
                with self.assertRaises(ValueError): cli.load(p)

    def test_fresh_replay_with_producer_imports_blocked(self):
        c, _ = bridge.infer(self.text, self.selection)
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/"case.json"; path.write_text(json.dumps([self.text,self.selection,c]))
            script = '''import importlib.abc,json,sys
sys.path.insert(0,sys.argv[1])
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname in {'subprocess','z3','pysmt'} or (fullname.startswith('research.') and fullname.rsplit('.',1)[-1] in {'producer','experiment'}):
   raise ImportError('blocked '+fullname)
sys.meta_path.insert(0,Block())
from research.signed_reduction.bridge import check_observations
s,r,c=json.load(open(sys.argv[2]));assert check_observations(s,r,c)['status']=='source_observation_verified'
'''
            # The assertion is not the test gate in optimized mode: output/check return and exit are.
            script = script.replace("assert check_observations(s,r,c)['status']=='source_observation_verified'",
                                    "result=check_observations(s,r,c);print(json.dumps(result))")
            for mode in ([],["-O"]):
                cp=subprocess.run([sys.executable,"-I","-B",*mode,"-c",script,str(ROOT),str(path)],capture_output=True,text=True)
                self.assertEqual(cp.returncode,0,cp.stderr)
                self.assertEqual(json.loads(cp.stdout)["status"],"source_observation_verified")


if __name__ == "__main__": unittest.main()
