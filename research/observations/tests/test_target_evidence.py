"""Replay the retained 23 actual-source formula packages; hashes are not proofs."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research.observations.model import digest
from research.observations.run_io import read_json
from research.observations.run_package import RunError, check_package
from research.observations.run_target_experiment import cases, run

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / 'research/observations/evidence/typed_targets'


class TargetEvidenceTests(unittest.TestCase):
    def test_all_retained_packages_replay_against_independent_goals(self):
        result = run(EVIDENCE, replay=True)
        self.assertEqual(len(result['cases']), 23)
        self.assertEqual(result['counts'], {
            'legacy_translation': {'certified': 11, 'refuted': 7},
            'new_formula': {'certified': 3, 'refuted': 2},
        })
        manifest = read_json(EVIDENCE / 'MANIFEST.json')
        actual = {p.relative_to(EVIDENCE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(EVIDENCE.rglob('*')) if p.is_file() and p.name != 'MANIFEST.json'}
        self.assertEqual(manifest, actual)
        for case in cases():
            directory = EVIDENCE / case['id']
            self.assertEqual((directory / 'source.java').read_bytes(), case['source'].encode('utf-8'))
            self.assertEqual(read_json(directory / 'goal.json'), case['goal'])
            package = read_json(directory / 'package.json', package=True)
            replayed = check_package(case['source'], case['goal'], package)
            self.assertEqual(read_json(directory / 'result.json'), replayed)

    def test_retained_proof_is_checked_after_rehashing(self):
        case = next(c for c in cases() if c['id'] == 'ascending.original.cyclic_successor')
        package = deepcopy(read_json(EVIDENCE / case['id'] / 'package.json', package=True))
        proof = package['proofs']['property']
        proof['states'].pop()
        package['binding']['property_certificate_sha256'] = digest(proof)
        with self.assertRaises(RunError) as error:
            check_package(case['source'], case['goal'], package)
        self.assertEqual(error.exception.status, 'invalid_certificate')

    def test_retained_check_and_explain_without_producer_templates_or_old_goals(self):
        data = [[c['source'], c['goal'],
                 read_json(EVIDENCE / c['id'] / 'package.json', package=True)] for c in cases()]
        code = '''
import builtins, json, sys
with open(sys.argv[1], encoding='utf-8') as stream: data = json.load(stream)
original = builtins.__import__
def guarded(name, *args, **kwargs):
    parts = name.split('.')
    blocked = {'target_templates', 'property_kernel', 'successor_kernel', 'upper_spec',
               'successor_spec', 'ascending_validation', 'property_validation',
               'run_unified_experiment', 'run_target_experiment', 'graal', 'subprocess',
               'z3', 'cvc5', 'pysmt', 'bitwuzla', 'sympy'}
    if any('producer' in p or p in blocked for p in parts):
        raise AssertionError('forbidden replay dependency: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from research.observations.run_package import check_package, explain_package
results = []
for source, goal, package in data:
    result = check_package(source, goal, package)
    explanation = explain_package(source, goal, package)
    if result['status'] != explanation['status'] or not explanation['explanation']['replayed']:
        raise AssertionError('unreplayed explanation')
    results.append(result['status'])
print(json.dumps(results))
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'packages.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            expected = [c['expected'] for c in cases()]
            for flags in ([], ['-O']):
                result = subprocess.run([sys.executable, *flags, '-c', code, str(path)],
                                        cwd=ROOT, text=True, capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), expected)


if __name__ == '__main__':
    unittest.main()
