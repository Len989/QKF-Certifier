"""Full-repository source/target regression. No mocked source adapters here.

These tests require the actual research source modules and retained evidence.
They are separate from the unit tests on declared toy source machines.
"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research.observations.model import digest
from research.observations.run_package import (
    SCHEMA, TYPED_SCHEMA, RunError, check_package, create_package, explain_package,
)
from research.observations.run_producer import verify
from research.observations.run_unified_experiment import retained_cases
from research.observations.target_kernel import check
from research.observations.target_producer import synthesize
from research.observations.target_rules import compile_spec
from research.observations.target_templates import from_legacy, template

ROOT = Path(__file__).resolve().parents[3]


class TargetSourceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = []
        for old in retained_cases():
            legacy = create_package(old['source'], old['spec'], old['profile'],
                                    old['source_certificate'], old['property_certificate'])
            spec = from_legacy(old['spec'])
            proposal = synthesize(old['source'], old['source_certificate'], spec)
            if proposal['status'] != 'candidate': raise AssertionError(proposal)
            proof = proposal['certificate']
            package = create_package(old['source'], spec, old['profile'], old['source_certificate'], proof)
            cls.cases.append({**old, 'legacy_package': legacy, 'goal': spec, 'proof': proof, 'package': package})

    def test_all_eighteen_old_verdicts_preserved_under_explicit_translation(self):
        self.assertEqual(len(self.cases), 18)
        counts = {'certified': 0, 'refuted': 0}
        for case in self.cases:
            old = check_package(case['source'], case['spec'], case['legacy_package'])
            new = check_package(case['source'], case['goal'], case['package'])
            self.assertEqual(old['status'], case['expected'])
            self.assertEqual(new['status'], old['status'], case['id'])
            self.assertEqual(case['legacy_package']['schema'], SCHEMA)
            self.assertEqual(case['package']['schema'], TYPED_SCHEMA)
            self.assertEqual(new['claim'], 'word_observation_formula')
            counts[new['status']] += 1
        self.assertEqual(counts, {'certified': 11, 'refuted': 7})

    def test_new_changes_combination_on_actual_five_ascending_sources(self):
        for case in self.cases:
            if case['profile'] != 'ascending' or case['spec']['claim'] != 'cyclic_successor': continue
            spec = template('ascending', 'changes')
            proposal = synthesize(case['source'], case['source_certificate'], spec)
            self.assertEqual(proposal['status'], 'candidate')
            result = check(case['source'], case['source_certificate'], spec, proposal['certificate'])
            expected = 'refuted' if case['name'] in {'first_or', 'first_four_bits'} else 'certified'
            self.assertEqual(result['status'], expected, case['id'])

    def test_fresh_source_inference_and_common_verify_in_both_profiles(self):
        for name in ('ascending.original.cyclic_successor', 'ascending.first_or.cyclic_successor',
                     'descending.original.maximum', 'descending.strict.maximum'):
            case = next(c for c in self.cases if c['id'] == name)
            result, package = verify(case['source'], case['goal'], profile=case['profile'])
            self.assertIsNotNone(package)
            self.assertEqual(result['status'], case['expected'])
            self.assertEqual(result, check_package(case['source'], case['goal'], package))
            self.assertEqual(digest(package), digest(case['package']))

    def test_upper_contract_does_not_silently_require_must_subset_seed(self):
        case = next(c for c in self.cases if c['id'] == 'descending.original.maximum')
        spec = deepcopy(case['goal'])
        spec['obligations'] = [['subset', 'must', 'output']]
        proof = synthesize(case['source'], case['source_certificate'], spec)['certificate']
        result = check(case['source'], case['source_certificate'], spec, proof)
        self.assertEqual(result['status'], 'refuted')
        values = result['counterexample']
        self.assertNotEqual(values['must'] & values['output'], values['must'])

    def test_corrupted_actual_source_proofs_and_source_bytes_are_rejected(self):
        for name in ('ascending.original.cyclic_successor', 'descending.original.maximum'):
            case = next(c for c in self.cases if c['id'] == name)
            with self.assertRaises(RunError):
                check_package(case['source'] + '\n', case['goal'], case['package'])
            changed = deepcopy(case['package'])
            changed['proofs']['source']['schema'] = 'wrong-source-proof'
            changed['binding']['source_certificate_sha256'] = digest(changed['proofs']['source'])
            with self.assertRaises(RunError): check_package(case['source'], case['goal'], changed)
            changed = deepcopy(case['package'])
            changed['proofs']['property']['program']['obligations'] = [True]
            changed['binding']['property_certificate_sha256'] = digest(changed['proofs']['property'])
            with self.assertRaises(RunError): check_package(case['source'], case['goal'], changed)

    def test_mask_breaking_source_is_not_assumed_legal_by_new_target(self):
        from research.observations.ascending_source import extract_region
        from research.observations.ascending_producer import synthesize as source_synthesize
        case = next(c for c in self.cases if c['id'] == 'ascending.original.cyclic_successor')
        region = extract_region(case['source'])['code']
        self.assertEqual(region.count('newLowerBound |= bit;'), 1)
        source = case['source'].replace(region, region.replace('newLowerBound |= bit;', 'newLowerBound &= ~bit;'))
        model = source_synthesize(source)['certificate']
        spec = template('ascending', 'membership')
        proof = synthesize(source, model, spec)['certificate']
        result = check(source, model, spec, proof)
        self.assertEqual(result['status'], 'refuted')
        values = result['counterexample']
        self.assertNotEqual(values['output'] & values['must'], values['must'])

    def test_untemplated_formula_and_positive_width_boundary(self):
        case = next(c for c in self.cases if c['id'] == 'ascending.original.membership')
        spec = deepcopy(case['goal'])
        spec['obligations'] = [['and', ['ne', 'ones', 'zero'],
            ['eq', ['bit_xor', 'output', 'output'], 'zero'],
            ['disjoint', 'output', ['bit_not', 'may']]]]
        proof = synthesize(case['source'], case['source_certificate'], spec)['certificate']
        self.assertEqual(check(case['source'], case['source_certificate'], spec, proof)['status'], 'certified')
        self.assertEqual(len(compile_spec(spec)['atoms']), 3)

    def test_fresh_replay_blocks_new_search_templates_old_goal_kernels_and_native_modules(self):
        data = [[case['source'], case['goal'], case['package']] for case in self.cases]
        code = '''
import builtins, json, sys
with open(sys.argv[1], encoding="utf-8") as stream: packages = json.load(stream)
original_import = builtins.__import__
def guarded(name, *args, **kwargs):
    pieces = name.split(".")
    blocked = {"target_templates", "property_kernel", "successor_kernel", "upper_spec", "successor_spec",
               "ascending_validation", "property_validation", "run_unified_experiment", "graal",
               "subprocess", "z3", "cvc5", "pysmt", "bitwuzla", "sympy"}
    if any("producer" in p or p in blocked for p in pieces):
        raise AssertionError("unexpected replay dependency: " + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded
from research.observations.run_package import check_package, explain_package, RunError
statuses = []
for source, goal, package in packages:
    result = check_package(source, goal, package)
    explanation = explain_package(source, goal, package)
    if not explanation["explanation"]["replayed"]: raise AssertionError("unreplayed explanation")
    statuses.append(result["status"])
source, goal, package = packages[0]
package["proofs"]["property"]["program"]["obligations"] = [True]
try: check_package(source, goal, package)
except RunError as exc:
    if exc.status != "invalid_certificate": raise
else: raise AssertionError("corruption accepted")
print(json.dumps(statuses))
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'packages.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            for flags in ([], ['-O']):
                result = subprocess.run([sys.executable, *flags, '-c', code, str(path)], cwd=ROOT,
                                        text=True, capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), [c['expected'] for c in self.cases])


if __name__ == '__main__': unittest.main()
