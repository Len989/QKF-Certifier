"""Conditional composition cross-checks. Only the real Lean job proves theorems."""
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.lean_targets import check_ceiling as bridge
from research.observations.ascending_kernel import Runner
from research.observations.ascending_validation import input_word
from research.observations.composition_program import execute, program

ROOT = Path(__file__).resolve().parents[3]


def complete_audit(axioms='propext, Quot.sound'):
    return '\n'.join("'" + n + "' depends on axioms: [" + axioms + ']' for n in bridge.THEOREMS)


def masks(width):
    for symbols in itertools.product((0, 1, 3), repeat=width):
        must = sum((s == 3) << i for i, s in enumerate(symbols))
        may = sum((s != 0) << i for i, s in enumerate(symbols))
        yield must, may


def members(width, must, may):
    return [z for z in range(1 << width) if z & must == must and z & ~may == 0]


def semantic_compose(minimum, maximum, bound, floor, successor):
    if bound < minimum:
        return minimum
    if maximum < bound:
        return None
    g = floor(bound)
    return g if g == bound else successor(g)


class CeilingBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = ROOT / 'research/observations/evidence/ascending'
        cls.runners = []
        for name in ('original', 'irrelevant_register'):
            cls.runners.append(Runner((base / (name + '.java')).read_text(),
                                      json.loads((base / (name + '.certificate.json')).read_text())))

    def test_audit_population_required(self):
        self.assertEqual(len(bridge.audit_output(complete_audit())), 22)
        for bad in (complete_audit().split('\n', 1)[1], complete_audit() + '\n' + complete_audit().splitlines()[0]):
            with self.assertRaises(ValueError):
                bridge.audit_output(bad)

    def test_unexpected_axioms_rejected(self):
        for axiom in ('sorryAx', 'Classical.choice', 'unprovedFloor', 'Lean.trustCompiler'):
            with self.subTest(axiom=axiom), self.assertRaises(ValueError):
                bridge.audit_output(complete_audit('propext, ' + axiom))

    def test_empty_axioms_and_absent_audit_are_distinct(self):
        text = '\n'.join("'" + n + "' does not depend on any axioms" for n in bridge.THEOREMS)
        self.assertTrue(all(v == [] for v in bridge.audit_output(text).values()))
        with self.assertRaises(ValueError):
            bridge.audit_output('Build completed successfully')

    def test_control_population_and_types(self):
        self.assertEqual(len(bridge.CONTROLS), 8)
        for name in bridge.CONTROLS:
            for expected in (False, True):
                self.assertIn('= ' + str(expected).lower() + ' := by decide', bridge.control_text(name, expected))
        for name, expected in (('unknown', True), ('positiveExamples', 1)):
            with self.assertRaises(ValueError):
                bridge.control_text(name, expected)

    def test_only_decision_proof_rejection_counts(self):
        info = dict(status='failed', stdout='error: Tactic decide proved the proposition is false', stderr='')
        self.assertTrue(bridge.proof_rejected(info))
        for status in ('success', 'unavailable', 'timeout'):
            self.assertFalse(bridge.proof_rejected({**info, 'status': status}))
        for msg in ('unknown identifier', 'unknown constant', 'unexpected token', 'file not found',
                    'unknown module', 'maximum recursion', 'maximum number of steps', 'failed to synthesize'):
            self.assertFalse(bridge.proof_rejected({**info, 'stderr': msg}))

    def test_missing_lean_is_not_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'result'
            with patch.object(bridge.shutil, 'which', return_value=None):
                result = bridge.validate(output)
            self.assertEqual(result['status'], 'unavailable')
            self.assertIs(result['lean_checked'], False)
            self.assertIs(result['conditional_floor_contract'], True)
            self.assertIs(result['json_interpreter_verified'], False)
            self.assertEqual(result['source_binding']['status'], 'source_factor_replayed')
            self.assertEqual(json.loads((output / 'RESULT.json').read_text())['status'], 'unavailable')

    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            saved = output / 'RESULT.json'
            saved.write_text('preserve')
            with self.assertRaises(FileExistsError):
                bridge.validate(output)
            self.assertEqual(saved.read_text(), 'preserve')

    def test_budget_validated_before_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            for budget in (True, 0, -1, 901):
                output = Path(tmp) / str(budget)
                with self.assertRaises(ValueError):
                    bridge.validate(output, timeout=budget)
                self.assertFalse(output.exists())

    def test_audit_and_control_declarations_match_driver(self):
        root = ROOT / 'research/lean_targets'
        text = (root / 'CeilingAudit.lean').read_text()
        self.assertEqual(tuple(line.split()[-1] for line in text.splitlines() if line.startswith('#print axioms ')), bridge.THEOREMS)
        controls = (root / 'QKFTarget/CeilingControls.lean').read_text()
        for name in bridge.CONTROLS:
            self.assertIn('def ' + name + ' : Bool :=', controls)

    def test_optional_extension_carrier(self):
        count = 0
        for width in range(1, 6):
            for must, may in masks(width):
                optional = may & ~must
                extensions = {must | s for s in range(1 << width) if s & ~optional == 0}
                self.assertEqual(extensions, set(members(width, must, may)))
                self.assertEqual(min(extensions), must)
                self.assertEqual(max(extensions), may)
                count += 1
        self.assertEqual(count, 363)

    def test_reseed_preserves_masks_and_actual_factor_answer(self):
        count = 0
        for width in range(1, 6):
            for original in itertools.product(range(4), repeat=width):
                must = sum((i == 3) << k for k, i in enumerate(original))
                may = sum((i != 0) << k for k, i in enumerate(original))
                legal = members(width, must, may)
                for g in legal:
                    reseeded = [3 if i == 3 else (2 if (g >> k) & 1 else 1) if i != 0 else 0
                                for k, i in enumerate(original)]
                    self.assertEqual([i == 3 for i in reseeded], [i == 3 for i in original])
                    self.assertEqual([i != 0 for i in reseeded], [i != 0 for i in original])
                    self.assertEqual(sum((i in (2, 3)) << k for k, i in enumerate(reseeded)), g)
                    expected = next((z for z in legal if z > g), must)
                    for runner in self.runners:
                        answer = sum(int(b) << k for k, b in enumerate(runner.run(input_word((width, must, may, g)))['outputs']))
                        self.assertEqual(answer, expected)
                    count += 1
        self.assertEqual(count, 9330)

    def test_semantic_wrapper_agrees_with_published_json(self):
        # Numerical contracts are instantiated by finite oracles here. The
        # actual descending source theorem remains a separate obligation.
        count = 0
        for width in range(1, 6):
            for must, may in masks(width):
                legal = members(width, must, may)
                def floor(b):
                    return max(z for z in legal if z <= b)
                def successor(g):
                    return next((z for z in legal if z > g), must)
                for bound in range(1 << width):
                    def invoke(role, w, args):
                        self.assertEqual((w, args['must'], args['may']), (width, must, may))
                        if role == 'descending':
                            self.assertEqual(args['seed'], must)
                            return floor(args['bound'])
                        self.assertEqual(args['seed'], floor(bound))
                        return successor(args['seed'])
                    out = execute(program(), dict(width=width, must=must, may=may, bound=bound), invoke)['result']
                    result = semantic_compose(must, may, bound, floor, successor)
                    expected = next((z for z in legal if z >= bound), None)
                    self.assertEqual(result, expected)
                    self.assertEqual(out, {'kind': 'empty'} if result is None else {'kind': 'value', 'value': result})
                    count += 1
        self.assertEqual(count, 9330)

    def test_boundary_at_minimum_still_calls_floor(self):
        calls = []
        def floor(b):
            calls.append(b)
            return 0
        self.assertEqual(semantic_compose(0, 1, 0, floor, lambda _: 1), 0)
        self.assertEqual(calls, [0])
        text = (ROOT / 'research/lean_targets/QKFTarget/Ceiling.lean').read_text()
        self.assertIn('if bound < minimum then some minimum', text)
        self.assertEqual(program(), json.loads((ROOT / 'research/observations/composition_example.json').read_text()))

    def test_empty_zero_singleton_and_outside_word_bounds(self):
        self.assertEqual(semantic_compose(0, 0, 0, lambda _: 0, lambda _: 0), 0)
        self.assertIsNone(semantic_compose(0, 0, 1, lambda _: 0, lambda _: 0))
        self.assertEqual(semantic_compose(5, 5, 2, lambda _: 5, lambda _: 5), 5)
        self.assertIsNone(semantic_compose(5, 5, 2**4096, lambda _: 5, lambda _: 5))

    def test_bounded_but_nonmaximal_floor_is_not_enough(self):
        legal = [0, 1, 4, 5]
        successor = lambda g: next((z for z in legal if z > g), 0)
        result = semantic_compose(0, 5, 2, lambda _: 0, successor)
        self.assertEqual(result, 1)
        self.assertLess(result, 2)

    def test_source_bindings_and_deferred_frontend_independence(self):
        result = bridge.check_source_bindings()
        self.assertEqual(len(result['sources']), 2)
        self.assertFalse((ROOT / 'research/wordexpr').exists())
        # The committed existing proof modules must still match accepted bindings.
        self.assertEqual(result['status'], 'source_factor_replayed')


if __name__ == '__main__':
    unittest.main()
