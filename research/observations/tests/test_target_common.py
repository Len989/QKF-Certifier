"""Common-package and CLI unit tests using declared test machines, not Java."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
from types import ModuleType
import tempfile
import unittest
from unittest.mock import patch

from research.observations.tests import test_target_finite_kernel as machines
from research.observations.model import digest
from research.observations.run import main
from research.observations.run_package import (
    PROFILES, RunError, TYPED_SCHEMA, check_package, create_package, explain_package, profile_for,
)
from research.observations.run_producer import verify
from research.observations.target_templates import template


class TargetCommonTests(unittest.TestCase):
    def setUp(self):
        machines.TargetFiniteKernelTests.setUp(self)
        self.asc['schema'] = PROFILES['ascending']['source_schema']
        self.desc['schema'] = PROFILES['descending']['source_schema']
        def validator(profile, expected):
            def check_source(source, cert):
                if source not in {'test-successor', 'test-or', 'test-identity'} or digest(cert) != digest(expected):
                    raise ValueError('declared unit-test source model')
                return {'status': 'certified', 'claim': PROFILES[profile]['source_claim']}
            return check_source
        sys.modules['research.observations.ascending_kernel'].check = validator('ascending', self.asc)
        sys.modules['research.observations.source_factor'].check = validator('descending', self.desc)
        extra = {}
        for name in ('ascending_source', 'java_words'):
            module = ModuleType('research.observations.' + name)
            module.read_source = lambda source: {'unit_test_source': source}
            extra[module.__name__] = module
        producer = ModuleType('research.observations.ascending_producer')
        producer.synthesize = lambda source, **kwargs: {'status': 'candidate', 'certificate': deepcopy(self.asc)}
        extra[producer.__name__] = producer
        sys.modules['research.observations.source_factor'].synthesize = (
            lambda source, **kwargs: {'status': 'candidate', 'certificate': deepcopy(self.desc)})
        imports = patch.dict(sys.modules, extra)
        imports.start(); self.addCleanup(imports.stop)

    def test_v2_packages_recompute_both_claims_and_explanations(self):
        for profile, source, claim in (
            ('ascending', 'test-successor', 'cyclic_successor'),
            ('descending', 'test-identity', 'bound'),
        ):
            spec = template(profile, claim)
            result, package = verify(source, spec, profile=profile)
            self.assertEqual(result['status'], 'certified')
            self.assertEqual(package['schema'], TYPED_SCHEMA)
            self.assertEqual(check_package(source, spec, package), result)
            explanation = explain_package(source, spec, package)
            self.assertTrue(explanation['explanation']['replayed'])
            self.assertTrue(explanation['explanation']['derived_observations'])
            self.assertEqual(explanation['explanation']['domain'], spec['domain'])

    def test_negative_packages_are_not_positive_verdicts(self):
        spec = template('ascending', 'cyclic_successor')
        result, package = verify('test-or', spec, profile='ascending')
        self.assertEqual(result['status'], 'refuted')
        package['result']['status'] = 'certified'
        with self.assertRaises(RunError) as caught: check_package('test-or', spec, package)
        self.assertEqual(caught.exception.status, 'invalid_certificate')

    def test_external_specification_and_package_versions_cannot_be_substituted(self):
        spec = template('ascending', 'membership')
        _, package = verify('test-successor', spec, profile='ascending')
        for key, value in [('schema', 'qkf-research-package-v1'), ('profile', 'descending')]:
            changed = deepcopy(package); changed[key] = value
            with self.assertRaises(RunError): check_package('test-successor', spec, changed)
        with self.assertRaises(RunError): profile_for(spec, 'descending')
        spec['preconditions'] = [['eq', 'output', 'seed']]
        with self.assertRaises(RunError) as caught: profile_for(spec)
        self.assertEqual(caught.exception.status, 'input_error')

    def test_common_cli_supports_template_verify_check_and_explain(self):
        def cli(*args):
            output = io.StringIO()
            with redirect_stdout(output): code = main(list(map(str, args)))
            return code, json.loads(output.getvalue())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, spec, result_dir = root / 'source.java', root / 'goal.json', root / 'result'
            source.write_text('test-successor', encoding='utf-8')
            code, result = cli('spec', spec, '--profile', 'ascending', '--claim', 'changes', '--language', 'observations')
            self.assertEqual((code, result['status']), (0, 'written'))
            code, result = cli('verify', source, '--profile', 'ascending', '--spec', spec, '--output', result_dir)
            self.assertEqual((code, result['status']), (0, 'certified'))
            for command in ('check', 'explain'):
                code, result = cli(command, source, '--spec', spec, '--package', result_dir / 'package.json')
                self.assertEqual((code, result['status']), (0, 'certified'))
            saved = spec.read_bytes()
            self.assertEqual(cli('spec', spec, '--profile', 'ascending', '--claim', 'changes', '--language', 'observations')[0], 64)
            self.assertEqual(spec.read_bytes(), saved)

    def test_common_budgets_still_return_no_package(self):
        spec = template('ascending', 'cyclic_successor')
        result, package = verify('test-successor', spec, profile='ascending', budgets={'property': {'max_states': 1}})
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertIsNone(package)


if __name__ == '__main__': unittest.main()
