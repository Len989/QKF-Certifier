"""Real frozen proofs, lossless evidence storage, and producer-free replay."""
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
from research.observations.run_target_experiment import cases
from research.observations.target_evidence import (
    CASE_IDS, ROOT, SNAPSHOT, compare_fresh, load_case, load_snapshot, materialize,
)


class TargetEvidenceTests(unittest.TestCase):
    def test_all_retained_packages_replay_against_independent_goals(self):
        expected = {c['id']: c for c in cases()}
        self.assertEqual(set(expected), set(CASE_IDS))
        counts = {'certified': 0, 'refuted': 0}
        for ident in CASE_IDS:
            source, goal, package = load_case(ident)
            self.assertEqual(source, expected[ident]['source'])
            self.assertEqual(goal, expected[ident]['goal'])
            result = check_package(source, goal, package)
            self.assertEqual(result['status'], expected[ident]['expected'])
            counts[result['status']] += 1
        self.assertEqual(counts, {'certified': 14, 'refuted': 9})
        self.assertEqual(hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest(),
                         'c63e2c0fb202b8857ee9fc1fdda7dc67e0786b258327ceea6b044b91f4ad0f60')

    def test_retained_proof_is_checked_before_its_digest(self):
        snapshot = load_snapshot()
        entry = snapshot['cases']['ascending.original.cyclic_successor']
        entry['certificate']['states'].pop()
        # Even guessing a different envelope digest does not bypass replay.
        entry['package_sha256'] = '0' * 64
        with self.assertRaises(RunError):
            load_case('ascending.original.cyclic_successor', snapshot=snapshot)

    def test_snapshot_paths_and_bindings_are_rejected(self):
        for field, value in (('source', '../outside.java'),
                             ('source_certificate', '/tmp/other.json'),
                             ('source_sha256', '0' * 64),
                             ('source_certificate_sha256', '0' * 64)):
            snapshot = load_snapshot()
            snapshot['sources']['ascending.original'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                load_case('ascending.original.cyclic_successor', snapshot=snapshot)
        for ident in ('../original', 'ascending.unknown.changes'):
            with self.assertRaises(ValueError): load_case(ident)

    def test_snapshot_population_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'snapshot.json'
            snapshot = load_snapshot(); snapshot['cases'].pop(next(iter(snapshot['cases'])))
            p.write_text(json.dumps(snapshot))
            with self.assertRaises(ValueError): load_snapshot(p)
            p.write_text('{"schema":1,"schema":2}')
            with self.assertRaises(RunError): load_snapshot(p)

    def test_shared_program_still_recompiled_from_external_goal(self):
        ident = 'ascending.original.cyclic_successor'
        snapshot = load_snapshot(); entry = snapshot['cases'][ident]
        altered = deepcopy(snapshot['programs'][entry['program']])
        altered['obligations'] = [True]
        key = digest(altered); snapshot['programs'][key] = altered; entry['program'] = key
        with self.assertRaises(RunError): load_case(ident, snapshot=snapshot)

    def test_materialization_is_lossless_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'evidence'
            result = materialize(output)
            self.assertEqual(result['packages'], 23)
            self.assertEqual(compare_fresh(output)['packages'], 23)
            manifest = read_json(output / 'MANIFEST.json')
            actual = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in output.rglob('*') if p.is_file() and p.name != 'MANIFEST.json'}
            self.assertEqual(manifest, actual)
            with self.assertRaises(FileExistsError): materialize(output)
            source = output / 'ascending.original.cyclic_successor/source.java'
            source.write_bytes(source.read_bytes() + b'\n')
            with self.assertRaises(ValueError): compare_fresh(output)

    def test_retained_check_and_explain_without_producer_templates_or_old_goals(self):
        code = '''
import builtins, json
original = builtins.__import__
def guarded(name, *args, **kwargs):
    parts = name.split('.')
    blocked = {'target_templates', 'property_kernel', 'successor_kernel', 'upper_spec',
               'successor_spec', 'ascending_validation', 'property_validation',
               'run_unified_experiment', 'run_target_experiment', 'graal', 'subprocess',
               'z3', 'cvc5', 'pysmt', 'bitwuzla', 'sympy'}
    if any('producer' in p or p.startswith('composition_') or p in blocked for p in parts):
        raise AssertionError('forbidden replay dependency: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from research.observations.target_evidence import CASE_IDS, load_case
from research.observations.run_package import check_package, explain_package
results = []
for ident in CASE_IDS:
    source, goal, package = load_case(ident)
    result = check_package(source, goal, package)
    explanation = explain_package(source, goal, package)
    if result['status'] != explanation['status'] or not explanation['explanation']['replayed']:
        raise AssertionError('unreplayed explanation')
    results.append(result['status'])
print(json.dumps(results))
'''
        expected = [load_case(i)[2]['result']['status'] for i in CASE_IDS]
        for flags in ([], ['-O']):
            result = subprocess.run([sys.executable, *flags, '-c', code], cwd=ROOT,
                                    text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), expected)


if __name__ == '__main__': unittest.main()
