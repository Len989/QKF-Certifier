"""Risks in experimental attribution, complete denominators and proof replay."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from .common import (ROOT, canonical, digest, save_json, load_json, identity,
                     compare_identity, matched_verdicts, validate_attempts, validate_case,
                     registered, inventory, check_inventory)


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from .fixtures import cases
        from .worker import run
        cls.case = next(c for c in cases() if c['name'] == 'mask_31')
        cls.saved = run(cls.case, 'sdk_default', audit=True)

    def test_real_source_trace_and_proof(self):
        from .verify import verify_record
        checked = verify_record(self.case, 'sdk_default', self.saved)
        self.assertEqual(checked['packets'], 1)
        self.assertGreater(checked['checkpoints'], 0)
        self.assertEqual(checked['warm_apply_calls'], len(self.case['applications']))
        self.assertGreater(self.saved['trace']['counts']['research_calls'],
                           self.saved['work']['backend']['counts']['research_calls'])
        self.assertEqual(self.saved['trace']['counts'].get('legacy_coverage_builds', 0), 0)
        self.assertTrue(self.saved['trace']['closure_trace'])

    def test_fresh_search_free_optimized_verifier(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            p = Path(directory)
            save_json(p/'case.json', self.case)
            save_json(p/'saved.json', self.saved)
            result = subprocess.run([sys.executable, '-O', '-B', '-m', 'research.causal_comparison.verify',
                str(p/'case.json'), 'sdk_default', str(p/'saved.json'), str(p/'check.json'), '--history'],
                cwd=ROOT, text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(load_json(p/'check.json')['search_imports'], 0)

    def test_changed_source_with_same_saved_result_rejected(self):
        from .verify import verify_record
        case = deepcopy(self.case)
        case['source'] = case['source'].replace('(x & 1) == 0', '(x & 1) == 1')
        with self.assertRaises(ValueError):
            verify_record(case, 'sdk_default', self.saved)

    def test_execution_table_tamper_rehashed_rejected(self):
        from research.signed_compact.dag import unpack, pack
        from .verify import verify_record
        saved = deepcopy(self.saved)
        data = unpack(saved['certificate'])
        data['interface']['values'][0] = not data['interface']['values'][0]
        saved['certificate'] = pack(data)
        saved['identity'] = identity(saved)
        with self.assertRaises(ValueError):
            verify_record(self.case, 'sdk_default', saved)

    def test_timed_proof_drift_rejected(self):
        trial = dict(identity=deepcopy(self.saved['identity']))
        trial['identity']['certificate_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            compare_identity(self.saved, trial)

    def test_timed_status_drift_rejected(self):
        trial = dict(identity=deepcopy(self.saved['identity']))
        trial['identity']['status'] = 'refuted'
        with self.assertRaises(ValueError):
            compare_identity(self.saved, trial)

    def test_historical_foundation_tamper_rejected(self):
        from .verify import verify_record
        saved = deepcopy(self.saved)
        saved['work']['backend']['checkpoints'][0]['id'] = '0' * 64
        with self.assertRaises(ValueError):
            verify_record(self.case, 'sdk_default', saved)

    def test_hidden_build_claim_rejected(self):
        from .analysis import causal_checks
        saved = deepcopy(self.saved)
        saved['trace']['counts']['legacy_coverage_builds'] = 1
        with self.assertRaises(ValueError):
            causal_checks(self.case, {'sdk_default': saved})


class AttributionTests(unittest.TestCase):
    def test_changed_native_basis_invalidates_backend_comparison(self):
        from .analysis import causal_checks
        a = dict(work=dict(fact_attempts=[], ground_request_sha256='a', counts={}))
        b = dict(work=dict(fact_attempts=[{'candidate': 1}], ground_request_sha256='a', counts={}))
        with self.assertRaises(ValueError):
            causal_checks({}, {'direct41': a, 'query41': b})

    def test_changed_query_invalidates_backend_comparison(self):
        from .analysis import causal_checks
        a = dict(work=dict(fact_attempts=[], ground_request_sha256='a', counts={}))
        b = dict(work=dict(fact_attempts=[], ground_request_sha256='b', counts={}))
        with self.assertRaises(ValueError):
            causal_checks({}, {'direct41': a, 'query41': b})

    def test_unresolved_is_not_source_refutation(self):
        matched_verdicts(['certified', 'unresolved', 'budget_exhausted', 'unsupported'])
        matched_verdicts(['refuted', 'unresolved'])
        with self.assertRaises(ValueError):
            matched_verdicts(['certified', 'refuted'])

    def test_legacy_contract_is_not_silently_weakened(self):
        from .fixtures import cases
        from .worker import execute
        case = next(c for c in cases() if c['name'] == 'mask_fixed_alias')
        with self.assertRaises(ValueError):
            execute(case, 'retained')


class DenominatorTests(unittest.TestCase):
    def setUp(self):
        self.reg = dict(cases=[dict(name='one', routes=['a', 'b'], unavailable={'b': 'fixed width'})])
        self.attempts = [dict(case='one', route='a', trial=t, operation=o, status='passed')
                         for t in ('audit', 0, 1, 2) for o in ('build', 'check')]
        self.attempts.append(dict(case='one', route='a', trial='memory', operation='build', status='passed'))

    def test_full_attempt_set(self):
        validate_attempts(self.attempts, self.reg, 3)

    def test_running_ledger_keeps_previous_attempts(self):
        from .common import checkpoint_json
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / 'ATTEMPTS.json'
            checkpoint_json(path, self.attempts[:1])
            checkpoint_json(path, self.attempts[:2])
            self.assertEqual(load_json(path), self.attempts[:2])
            self.assertFalse(path.with_name(path.name + '.pending').exists())

    def test_failed_attempt_remains_in_denominator(self):
        self.attempts[0]['status'] = 'failed'
        validate_attempts(self.attempts, self.reg, 3)

    def test_missing_trial_rejected(self):
        with self.assertRaises(ValueError):
            validate_attempts(self.attempts[:-1], self.reg, 3)

    def test_duplicate_trial_cannot_replace_missing_one(self):
        self.attempts[-1] = deepcopy(self.attempts[0])
        with self.assertRaises(ValueError):
            validate_attempts(self.attempts, self.reg, 3)

    def test_unavailable_arm_cannot_replace_measured_arm(self):
        self.attempts[0]['route'] = 'b'
        with self.assertRaises(ValueError):
            validate_attempts(self.attempts, self.reg, 3)

    def test_unknown_case_cannot_replace_measured_case(self):
        self.attempts[0]['case'] = 'unknown'
        with self.assertRaises(ValueError):
            validate_attempts(self.attempts, self.reg, 3)

    def test_registered_case_change_rejected(self):
        from .fixtures import cases
        _, reg = registered()
        rows = list(cases())
        for c, entry in zip(rows, reg['cases']):
            validate_case(c, entry)
        rows[0]['expected']['sdk_default'] = 'unresolved'
        with self.assertRaises(ValueError):
            validate_case(rows[0], reg['cases'][0])

    def test_manifest_truncation_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            p = Path(directory)
            save_json(p/'proof.json', {'proof': 1})
            save_json(p/'MANIFEST.json', inventory(p))
            check_inventory(p)
            (p/'proof.json').unlink()
            with self.assertRaises(ValueError):
                check_inventory(p)

    def test_manifest_symlink_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            p = Path(directory)
            save_json(p/'proof.json', {'proof': 1})
            (p/'link').symlink_to(p/'proof.json')
            save_json(p/'MANIFEST.json', inventory(p))
            with self.assertRaises(ValueError):
                check_inventory(p)


if __name__ == '__main__':
    unittest.main()
