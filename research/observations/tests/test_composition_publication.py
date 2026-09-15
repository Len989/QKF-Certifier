"""Post-PR11 integration: fresh dependencies, real controls, and honest manifests."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from research.observations import run_composition_experiment as experiment
from research.observations.composition_execution import Execution
from research.observations.composition_kernel import check
from research.observations.composition_program import program
from research.observations.composition_producer import synthesize
from research.observations.composition_spec import specification
from research.observations.model import digest
from research.observations.run_io import read_json
from research.observations.tests.test_upstream_mask import with_mask


class CompositionPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from research.observations.run_target_experiment import run
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.fresh = cls.root / 'fresh'
        with redirect_stdout(io.StringIO()):
            run(cls.fresh)
        cls.population = tuple(experiment.cases(cls.fresh))
        cls.output = cls.root / 'composed'
        with redirect_stdout(io.StringIO()):
            experiment.run(cls.output, typed_evidence=cls.fresh, max_width=1)

    def test_consumes_fresh_packages_without_a_retained_package_fallback(self):
        original_read = experiment.read_json
        def guarded(path, **kwargs):
            p = Path(path)
            if p.name == 'package.json' and experiment.TYPED in p.parents:
                raise AssertionError('retained package fallback')
            return original_read(path, **kwargs)
        with patch.object(experiment, 'read_json', side_effect=guarded):
            with redirect_stdout(io.StringIO()):
                answer = experiment.run(self.output, replay=True, typed_evidence=self.fresh)
        self.assertEqual(answer['counts'], {'certified': 3, 'refuted': 13, 'unresolved': 1})

    def test_all_positive_dependencies_are_exactly_the_fresh_packages(self):
        for case in self.population:
            if case['expected'] != 'certified':
                continue
            certificate = read_json(self.output / case['id'] / 'certificate.json', package=True)
            self.assertEqual(certificate['dependencies'], case['dependencies'])
            self.assertEqual(check(case['program'], case['sources'], specification(), certificate)['status'], 'certified')
        self.assertEqual(experiment.verify_baseline(self.output)['matched_cases'], 17)

    def test_changed_source_or_goal_in_fresh_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'ascending.original.cyclic_successor'
            shutil.copytree(self.fresh / folder.name, folder)
            source = folder / 'source.java'
            original = source.read_bytes()
            source.write_bytes(original + b'\n')
            with self.assertRaisesRegex(ValueError, 'pinned composition source'):
                experiment.source_case('ascending', 'original', root)
            source.write_bytes(original)
            goal = folder / 'goal.json'
            data = json.loads(goal.read_text())
            data['preconditions'] = [False]
            goal.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'exact external region goal'):
                experiment.source_case('ascending', 'original', root)

    def test_rehashed_corruption_fails_mathematics_before_baseline_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'proofs'
            shutil.copytree(self.output, root)
            path = root / 'wrapper.original/certificate.json'
            certificate = read_json(path, package=True)
            certificate['cases'].pop()
            path.write_text(json.dumps(certificate))
            (root / 'MANIFEST.json').write_text(json.dumps(experiment.manifest(root)))
            with patch.object(experiment, 'verify_baseline', side_effect=AssertionError('hash gate reached first')):
                with redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, 'complete weak-order'):
                    experiment.run(root, replay=True, typed_evidence=self.fresh)

    def test_rehashed_dependency_provenance_is_recomputed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'proofs'
            shutil.copytree(self.output, root)
            path = root / 'DEPENDENCIES.json'
            record = read_json(path)
            record['wrapper.original']['ascending']['package_sha256'] = '0' * 64
            path.write_text(json.dumps(record))
            (root / 'MANIFEST.json').write_text(json.dumps(experiment.manifest(root)))
            with self.assertRaisesRegex(ValueError, 'dependency provenance'):
                experiment.run(root, replay=True, typed_evidence=self.fresh)

    def test_upstream_primitive_form_is_preserved_through_composition(self):
        case = self.population[0]
        sources = {role: with_mask(source) for role, source in case['sources'].items()}
        proposal = synthesize(program(), sources, specification())
        self.assertEqual(proposal['status'], 'candidate')
        certificate = proposal['certificate']
        result = check(program(), sources, specification(), certificate)
        self.assertEqual(result['status'], 'certified')
        self.assertEqual(result['checked_order_cases'], 1076)
        self.assertNotEqual(digest(certificate['dependencies']), digest(case['dependencies']))
        models = {r: p['proofs']['source'] for r, p in certificate['dependencies'].items()}
        runner = Execution(sources, models)
        for bound, expected in [(0, {'kind': 'value', 'value': 0}),
                                (2, {'kind': 'value', 'value': 4}),
                                (6, {'kind': 'empty'})]:
            answer = runner.run(program(), dict(width=3, must=0, may=5, bound=bound))
            self.assertEqual(answer['result'], expected)

    def test_unresolved_report_cannot_be_replayed_as_a_certificate(self):
        case = next(c for c in self.population if c['expected'] == 'unresolved')
        report = read_json(self.output / case['id'] / 'result.json', package=True)
        self.assertIsNone(report['certificate'])
        self.assertEqual(report['search']['tested_inputs'], 1554)
        with self.assertRaises(ValueError):
            check(case['program'], case['sources'], specification(), report)


if __name__ == '__main__':
    unittest.main()
