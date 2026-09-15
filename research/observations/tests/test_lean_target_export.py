"""Run-4 exporter/integration/timeout tests. These are NOT Lean kernel checks."""
from copy import deepcopy
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from research.observations.lean_target_export import (
    CASES, ROOT, build_export, check_export, export_all, inputs, render_all,
    render_case, successor_goal, validate_finite,
)
from research.observations.model import digest
from research.observations.run_lean_target_validation import (
    PROJECT, THEOREMS, audit_output, negative_mutations, run_command, validate,
)
from research.observations.run_package import RunError
from research.observations.target_rules import advance, concrete_violation, initial, violation


class LeanTargetExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.input = {name: inputs(name) for name in CASES}
        cls.exports = {name: build_export(*cls.input[name]) for name in CASES}

    def test_actual_source_packages_and_separate_scope(self):
        for name in CASES:
            result = check_export(*self.input[name], self.exports[name])
            self.assertEqual(result, dict(status='finite_export_checked', source_classes=2,
                                         states=9, transitions=54, lean_checked=False))
        self.assertEqual(self.exports['original']['machine'], self.exports['irrelevant_register']['machine'])
        self.assertNotEqual(self.exports['original']['binding']['source_sha256'],
                            self.exports['irrelevant_register']['binding']['source_sha256'])

    def test_retained_export_and_actual_lean_module_identity(self):
        result = export_all(PROJECT / 'evidence', check_existing=True)
        self.assertIs(result['lean_checked'], False)
        self.assertEqual((PROJECT / 'QKFTarget/Exported.lean').read_bytes(),
                         (PROJECT / 'evidence/Exported.lean').read_bytes())
        self.assertEqual(render_all(self.exports), (PROJECT / 'QKFTarget/Exported.lean').read_text())

    def test_new_output_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'exports'
            export_all(dest)
            export_all(dest, check_existing=True)
            before = (dest / 'Original.lean').exists()
            self.assertFalse(before)
            with self.assertRaises(FileExistsError): export_all(dest)
            p = dest / 'original.json'
            p.write_text('{}')
            with self.assertRaises(ValueError): export_all(dest, check_existing=True)

    def test_adversarial_export_data(self):
        changes = [
            lambda e: e.update(lean_checked=True),
            lambda e: e.update(initial=True),
            lambda e: e.update(initial=1),
            lambda e: e['alphabet'].pop(),
            lambda e: e['source_alphabet'].reverse(),
            lambda e: e['machine'].update(initial=True),
            lambda e: e['machine']['cells'][0][0].update(output=True),
            lambda e: e['machine']['cells'][0][0].update(next=99),
            lambda e: e['states'][0].__setitem__(1, True),
            lambda e: e['states'][0].__setitem__(2, 1),
            lambda e: e['states'].append(deepcopy(e['states'][0])),
            lambda e: e['states'].pop(),
            lambda e: e['edges'][0].__setitem__(0, 0),
            lambda e: e['edges'][0].__setitem__(0, True),
            lambda e: e['program'].update(obligations=[True]),
            lambda e: e.update(extra=1),
        ]
        for i, change in enumerate(changes):
            data = deepcopy(self.exports['original']); change(data)
            with self.subTest(change=i), self.assertRaises((ValueError, TypeError)):
                validate_finite(data)

    def test_source_binding_needs_full_replay_not_just_table_checks(self):
        data = deepcopy(self.exports['original'])
        data['binding']['source_sha256'] = '0' * 64
        validate_finite(data)  # Explicitly: a digest's format is not its provenance.
        with self.assertRaises(ValueError): check_export(*self.input['original'], data)
        with self.assertRaises(ValueError): check_export(*self.input['irrelevant_register'], self.exports['original'])

    def test_external_goal_cannot_be_replaced_by_weak_formula(self):
        source, goal, package = self.input['original']
        goal = deepcopy(goal); goal['obligations'] = [True]
        with self.assertRaises(ValueError): build_export(source, goal, package)
        package = deepcopy(package)
        proof = package['proofs']['property']; proof['states'].pop()
        package['binding']['property_certificate_sha256'] = digest(proof)
        with self.assertRaises(RunError): build_export(source, successor_goal(), package)

    def test_only_fixed_lean_tokens_are_emitted(self):
        for name in ('evil; import Unsafe', '../x', 'Original\naxiom bad : False'):
            with self.assertRaises(ValueError): render_case(name, self.exports['original'])
        self.assertNotIn('Phase', render_all(self.exports))
        self.assertNotIn('nativeStep', render_all(self.exports))
        self.assertIn('program_matches', render_all(self.exports))

    def test_numeric_observations_of_exported_factor(self):
        rng = random.Random(1509202604)
        for data in self.exports.values():
            program = data['program']
            for _ in range(100):
                width = rng.randint(1, 512)
                q = data['machine']['initial']; observed = initial(program)
                values = dict(width=width, must=0, may=0, seed=0, alternative=0, output=0)
                for i in range(width):
                    col = rng.choice(data['alphabet'])
                    c = data['machine']['cells'][q][data['source_alphabet'].index(col[:3])]
                    env = dict(zip(('must', 'may', 'seed', 'alternative'), map(int, col)))
                    env['output'] = int(c['output']); q = c['next']
                    observed = advance(program, observed, env)
                    for k, v in env.items(): values[k] += v << i
                self.assertIsNone(violation(program, observed))
                self.assertIsNone(concrete_violation(successor_goal(), values))
                expected = [values['must'] & ~values['output'] == 0,
                            values['output'] & ~values['may'] == 0,
                            values['seed'] == values['may'],
                            (values['seed'] > values['output']) - (values['seed'] < values['output']),
                            (values['seed'] > values['alternative']) - (values['seed'] < values['alternative']),
                            (values['output'] > values['alternative']) - (values['output'] < values['alternative']),
                            values['output'] == values['must']]
                self.assertEqual(list(observed), expected)

    def test_positive_width_is_not_empty_initialization(self):
        for data in self.exports.values():
            self.assertIs(data['states'][0][1], False)
            self.assertIs(data['states'][data['edges'][0][0]][1], True)
            self.assertNotEqual(data['edges'][0][0], 0)

    def test_legal_rival_does_not_control_source_machine(self):
        data = self.exports['original']
        self.assertEqual(data['alphabet'], ['0000', '0100', '0101', '0110', '0111', '1111'])
        self.assertEqual([data['source_alphabet'].index(c[:3]) for c in data['alphabet']], [0, 1, 1, 2, 2, 3])
        # All six columns are accounted for; no output bit is assumed legal here.
        for row in data['machine']['cells']: self.assertEqual(len(row), 4)

    def test_export_replay_with_search_old_goals_and_native_imports_blocked(self):
        code = '''
import builtins, json
original = builtins.__import__
def guarded(name, *args, **kwargs):
    parts = name.split('.')
    blocked = {'target_templates','property_kernel','successor_kernel','graal','subprocess',
               'ascending_validation','z3','cvc5','pysmt','bitwuzla'}
    if any('producer' in p or p in blocked for p in parts):
        raise AssertionError('unexpected dependency: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from research.observations.lean_target_export import export_all, ROOT
result = export_all(ROOT / 'research/lean_targets/evidence', check_existing=True)
print(json.dumps(result))
'''
        for flags in ([], ['-O']):
            result = subprocess.run([sys.executable, *flags, '-c', code], cwd=ROOT,
                                    text=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIs(json.loads(result.stdout)['lean_checked'], False)


class LeanValidationDriverTests(unittest.TestCase):
    def test_no_toolchain_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp, patch('shutil.which', return_value=None):
            result = validate(Path(tmp) / 'out', timeout=1)
            self.assertEqual(result['status'], 'unavailable')
            self.assertIs(result['lean_checked'], False)
            self.assertEqual(result['commands'], [])

    def test_complete_axiom_audit_and_missing_or_unsafe_entries(self):
        text = '\n'.join("'" + n + "' depends on axioms: [propext, Quot.sound]" for n in THEOREMS)
        self.assertEqual(len(audit_output(text)), 10)
        empty = '\n'.join("'" + n + "' does not depend on any axioms" for n in THEOREMS)
        self.assertTrue(all(v == [] for v in audit_output(empty).values()))
        for bad in (text.replace('propext', 'sorryAx', 1),
                    text.replace('propext', 'Lean.trustCompiler', 1),
                    '\n'.join(text.splitlines()[1:]), text + '\n' + text.splitlines()[0]):
            with self.assertRaises(ValueError): audit_output(bad)

    def test_real_child_timeout_is_bounded(self):
        before = time.monotonic()
        result = run_command([sys.executable, '-c', 'import time; time.sleep(10)'], ROOT, 0.1)
        self.assertEqual(result['status'], 'timeout')
        self.assertLess(time.monotonic() - before, 3)

    def test_timeout_and_missing_executable_have_no_success(self):
        self.assertEqual(run_command([sys.executable], ROOT, 0)['status'], 'timeout')
        self.assertEqual(run_command(['/no/qkf/lean'], ROOT, 1)['status'], 'unavailable')

    def test_negative_controls_are_present_and_change_exactly_one_file(self):
        controls = negative_mutations(PROJECT)
        self.assertEqual(len(controls), 5)
        self.assertEqual(len({n for n, _, _ in controls}), 5)
        for name, path, text in controls:
            self.assertNotEqual(text, (PROJECT / path).read_text(), name)
            self.assertNotIn('sorry', text)

    def test_driver_preserves_output_and_rejects_bad_budgets(self):
        with tempfile.TemporaryDirectory() as tmp:
            for budget in (True, 0, 901):
                with self.assertRaises(ValueError): validate(Path(tmp) / 'out', timeout=budget)
            with self.assertRaises(FileExistsError): validate(tmp)


if __name__ == '__main__': unittest.main()
