"""Delivery binding, natural reuse, negative boundaries and independent replay."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from .common import (ROOT, registered, validate_case, identity, members, delivery,
                     aggregate, validate_attempts, canonical)
from .fixtures import cases
from .worker import run
from .verify import verify_record


class ComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {c['name']: c for c in cases()}
        cls.anchor = cls.cases['batch_mask_all_1']
        cls.saved = run(cls.anchor, 'once_ordinary', audit=True)

    def mutate(self, function):
        saved = copy.deepcopy(self.saved)
        function(saved)
        saved['identity'] = identity(saved)
        with self.assertRaises((ValueError, KeyError, IndexError, TypeError)):
            verify_record(self.anchor, 'once_ordinary', saved)

    def test_registered_full_population(self):
        protocol, reg = registered()
        self.assertEqual((len(reg['cases']), sum(len(c['routes']) for c in reg['cases'])), (33, 164))
        self.assertEqual(protocol['measurement']['timing_repeats'], 7)
        for case, entry in zip(self.cases.values(), reg['cases']):
            validate_case(case, entry)

    def test_shards_partition_population(self):
        from .common import SHARDS
        names = [c['name'] for shard in SHARDS for c in registered(shard)[1]['cases']]
        self.assertEqual(sorted(names), sorted(self.cases))

    def test_preserve_old_sources_and_requests(self):
        from research.causal_comparison.fixtures import cases as old
        for c in old():
            self.assertEqual((c['source'], c['request'], c['limits']),
                             tuple(self.cases[c['name']][k] for k in ('source', 'request', 'limits')))

    def test_ordinary_adapter_provides_real_sdk(self):
        result = verify_record(self.anchor, 'once_ordinary', self.saved)
        self.assertEqual(result['packets'], 1)
        self.assertEqual(result['semantic']['answers'][0]['status'], 'certified')
        self.assertTrue(result['semantic']['exports'])
        self.assertGreater(result['warm_apply_calls'], 0)

    def test_once_services_all_sixteen(self):
        c = self.cases['batch_mask_all_16']
        saved = copy.deepcopy(self.saved)
        from .common import digest
        saved['certificate']['request_sha256'] = digest(c['request'])
        saved['identity'] = identity(saved)
        out = verify_record(c, 'once_ordinary', saved)
        self.assertEqual(len(out['semantic']['answers']), 16)
        self.assertEqual(out['packets'], 1)

    def test_independent_certificates_are_singletons(self):
        c = self.cases['batch_parity_all_4']
        saved = run(c, 'each_ordinary', audit=True)
        out = verify_record(c, 'each_ordinary', saved)
        self.assertEqual(out['packets'], 4)
        self.assertEqual(delivery(c, 'each_ordinary'), 'independent_certificates')
        from research.applicable_summary.checker import check
        for (request, _), packet in zip(members(c, 'each_ordinary'), saved['certificate']['packets']):
            self.assertEqual(len(request['query']['requests']), 1)
            self.assertEqual(check(c['source'], request, packet).result()['status'], 'certified')

    def test_source_substitution_rejected(self):
        c = copy.deepcopy(self.anchor)
        c['source'] = c['source'].replace('(x<0)', '(x>=0)')
        with self.assertRaises(ValueError):
            verify_record(c, 'once_ordinary', self.saved)

    def test_omitted_packet_rejected(self):
        self.mutate(lambda s: s['certificate']['packets'].clear())

    def test_delivery_substitution_rejected(self):
        self.mutate(lambda s: s['certificate'].__setitem__('delivery', 'independent_certificates'))

    def test_unknown_envelope_field_rejected(self):
        self.mutate(lambda s: s['certificate'].__setitem__('trusted', True))

    def test_request_binding_rejected(self):
        self.mutate(lambda s: s['certificate'].__setitem__('request_sha256', '0'*64))

    def test_result_tampering_rejected(self):
        self.mutate(lambda s: s['result']['members'][0].__setitem__('applicable', 1))

    def test_corrupt_inner_action_rejected(self):
        def corrupt(s):
            from research.signed_compact import dag
            inner = dag.unpack(s['certificate']['packets'][0])
            inner['interface']['values'][0] = not inner['interface']['values'][0]
            s['certificate']['packets'][0] = dag.pack(inner)
        self.mutate(corrupt)

    def test_missing_semantic_proof_rejected(self):
        self.mutate(lambda s: s['certificate']['packets'].__setitem__(0, None))

    def test_missing_history_member_rejected(self):
        self.mutate(lambda s: s['work']['members'].clear())

    def test_boundaries_in_fresh_search_free_process(self):
        c = self.cases['assess_boundaries']
        saved = run(c, 'once_ordinary', audit=True)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for name, value in [('case', c), ('saved', saved)]:
                (d / (name + '.json')).write_text(canonical(value))
            result = subprocess.run([sys.executable, '-B', '-m', 'research.sdk_comparison.verify',
                str(d/'case.json'), 'once_ordinary', str(d/'saved.json'), str(d/'out.json'), '--history', '--repetitions', '1'],
                cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            out = json.loads((d/'out.json').read_text())
            self.assertEqual(out['search_imports'], 0)
            self.assertEqual([r['status'] for r in out['semantic']['followups']], ['certified'] + ['unresolved'] * 5)

    def test_concrete_refutation_keeps_witness(self):
        c = self.cases['mask_mutant']
        out = verify_record(c, 'sdk_ordinary', run(c, 'sdk_ordinary', audit=True))
        self.assertEqual(out['packets'], 1)
        self.assertEqual(out['warm_apply_calls'], 0)

    def test_budget_is_nonsemantic_diagnostic(self):
        c = self.cases['fact_budget']
        saved = run(c, 'sdk_ordinary', audit=True)
        self.assertEqual(saved['result']['status'], 'unresolved')
        self.assertEqual(verify_record(c, 'sdk_ordinary', saved)['packets'], 0)

    def test_prior_nonconsequence_is_replayed(self):
        c = self.cases['power_unconditional']
        saved = run(c, 'sdk_ordinary', audit=True)
        self.assertEqual(saved['result']['status'], 'unresolved')
        self.assertEqual(verify_record(c, 'sdk_ordinary', saved)['warm_apply_calls'], 0)

    def test_attempt_denominator_rejects_missing_or_duplicate(self):
        entry = registered()[1]['cases'][0]
        reg = dict(cases=[entry])
        attempts = [dict(case=entry['name'], route=r, trial=t, operation=o)
                    for r in entry['routes'] for t in ['audit', 0] for o in ('build', 'check')]
        attempts += [dict(case=entry['name'], route=r, trial='memory', operation='build') for r in entry['routes']]
        validate_attempts(attempts, reg, 1)
        for bad in (attempts[:-1], attempts + attempts[:1]):
            with self.assertRaises(ValueError):
                validate_attempts(bad, reg, 1)

    def test_instrumentation_modes_cannot_be_combined(self):
        with self.assertRaises(ValueError):
            run(self.anchor, 'once_ordinary', audit=True, memory=True)


if __name__ == '__main__':
    unittest.main()
