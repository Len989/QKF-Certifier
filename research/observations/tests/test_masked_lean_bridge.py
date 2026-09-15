"""Driver controls and numerical cross-checks; only Lean proves the new theorems."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.lean_targets import check_masked as bridge
from research.observations.ascending_kernel import Runner
from research.observations.ascending_validation import input_word, keys, successor

ROOT = Path(__file__).resolve().parents[3]


def complete_audit(axioms='propext, Quot.sound'):
    return '\n'.join("'" + name + "' depends on axioms: [" + axioms + ']'
                     for name in bridge.THEOREMS)


class MaskedBridgeTests(unittest.TestCase):
    def test_all_sixteen_audit_entries_required(self):
        self.assertEqual(len(bridge.audit_output(complete_audit())), 16)
        with self.assertRaises(ValueError):
            bridge.audit_output(complete_audit().split('\n', 1)[1])
        with self.assertRaises(ValueError):
            bridge.audit_output(complete_audit() + '\n' + complete_audit().splitlines()[0])

    def test_unexpected_axioms_rejected(self):
        for axiom in ('sorryAx', 'Classical.choice', 'unprovedBridge', 'Lean.trustCompiler'):
            with self.subTest(axiom=axiom), self.assertRaises(ValueError):
                bridge.audit_output(complete_audit('propext, ' + axiom))

    def test_no_axioms_is_allowed_but_missing_is_not(self):
        text = '\n'.join("'" + n + "' does not depend on any axioms" for n in bridge.THEOREMS)
        self.assertTrue(all(v == [] for v in bridge.audit_output(text).values()))
        with self.assertRaises(ValueError):
            bridge.audit_output('Build completed successfully')

    def test_probe_population_and_boolean_types(self):
        self.assertEqual(len(bridge.CONTROLS), 8)
        for name in bridge.CONTROLS:
            for expected in (False, True):
                text = bridge.control_text(name, expected)
                self.assertIn('Controls.' + name, text)
                self.assertIn('= ' + str(expected).lower() + ' := by decide', text)
        for name, expected in (('unknown', True), ('positiveExamples', 1)):
            with self.assertRaises(ValueError):
                bridge.control_text(name, expected)

    def test_only_actual_semantic_rejection_counts(self):
        good = dict(status='failed', returncode=1, stdout='error: Tactic `decide` proved the proposition is false', stderr='')
        self.assertTrue(bridge.proof_rejected(good))
        for status in ('success', 'timeout', 'unavailable'):
            self.assertFalse(bridge.proof_rejected({**good, 'status': status}))
        for message in ('unknown identifier', 'unexpected token', 'unknown module',
                        'file not found', 'maximum recursion', 'maximum number of steps'):
            self.assertFalse(bridge.proof_rejected({**good, 'stderr': message}))

    def test_missing_tools_cannot_accept(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'result'
            with patch.object(bridge, 'check_source_bindings', return_value={'status': 'test-double'}), \
                 patch.object(bridge.shutil, 'which', return_value=None):
                result = bridge.validate(output)
            self.assertEqual(result['status'], 'unavailable')
            self.assertIs(result['lean_checked'], False)
            self.assertFalse(result['commands'])
            self.assertEqual(json.loads((output / 'RESULT.json').read_text())['status'], 'unavailable')

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            saved = output / 'RESULT.json'
            saved.write_text('keep me')
            with self.assertRaises(FileExistsError):
                bridge.validate(output)
            self.assertEqual(saved.read_text(), 'keep me')

    def test_budget_validation_precedes_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            for budget in (True, 0, -1, 901):
                output = Path(tmp) / str(budget)
                with self.assertRaises(ValueError):
                    bridge.validate(output, timeout=budget)
                self.assertFalse(output.exists())

    def test_finite_bitlist_carrier_agrees_with_numeric_masks(self):
        from itertools import product
        checked = 0
        for key in keys(3):
            width, must, may, seed = key
            legal = []
            for bs in product((0, 1), repeat=width):
                if all(((must >> i) & 1) <= b <= ((may >> i) & 1) for i, b in enumerate(bs)):
                    legal.append(sum(b << i for i, b in enumerate(bs)))
            expected = [z for z in range(1 << width) if z & must == must and not z & ~may]
            self.assertEqual(sorted(legal), expected)
            self.assertEqual(min(legal), must)
            self.assertEqual(max(legal), may)
            self.assertEqual(any(z > seed for z in legal), seed != may)
            checked += 1
        self.assertEqual(checked, 84)

    def test_source_factors_and_exact_numerical_endpoint(self):
        base = ROOT / 'research/observations/evidence/ascending'
        runners = []
        for name in ('original', 'irrelevant_register'):
            source = (base / (name + '.java')).read_bytes().decode('utf-8')
            certificate = json.loads((base / (name + '.certificate.json')).read_text())
            runners.append(Runner(source, certificate))
        tested = 0
        for key in keys(5):
            outputs = [sum(int(b) << i for i, b in enumerate(r.run(input_word(key))['outputs']))
                       for r in runners]
            self.assertEqual(outputs, [successor(key)] * 2)
            tested += 1
        self.assertEqual(tested, 1364)

    def test_lean_audit_names_match_driver(self):
        text = (ROOT / 'research/lean_targets/MaskedAudit.lean').read_text()
        listed = [line.split()[-1] for line in text.splitlines() if line.startswith('#print axioms ')]
        self.assertEqual(tuple(listed), bridge.THEOREMS)
        controls = (ROOT / 'research/lean_targets/QKFTarget/MaskedControls.lean').read_text()
        for name in bridge.CONTROLS:
            self.assertIn('def ' + name + ' : Bool :=', controls)


if __name__ == '__main__':
    unittest.main()
