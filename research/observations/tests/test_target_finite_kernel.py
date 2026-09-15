"""Unit controls for the generic finite closure checker, NOT a Java source proof.

The source adapters in these tests are explicitly declared tiny test machines.
Production source-front-end regression is in test_target_integration.py.
"""
from copy import deepcopy
from itertools import product
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

from research.observations.model import digest
from research.observations.target_kernel import System, check
from research.observations.target_producer import synthesize
from research.observations.target_rules import compile_spec
from research.observations.target_templates import template


class TestAscendingRunner:
    def __init__(self, source, certificate):
        self.initial = 1
        self.cells = {}
        for q in (0, 1):
            for symbol in ('000', '010', '011', '111'):
                must, may, seed = map(int, symbol)
                if may and not must:
                    if source == 'test-or':
                        y, nxt = seed | q, 0
                    else:
                        y, nxt = seed ^ q, seed & q
                else:
                    y, nxt = seed, q
                self.cells[q, symbol] = str(y), nxt


class TestDescendingRunner:
    def __init__(self, source, certificate):
        self.runner = self
        self.initial = 0
        self.queries = ['top']
        self.boundary = 'top'
        self.terminal = ['1', '0']
        self.alphabet = tuple(''.join(map(str, b)) for b in product((0, 1), repeat=4)
                              if not b[0] & b[1] and b[0] <= b[3] <= b[0] + b[1])
        self.cells = {(s, a): int(s == 1 or a[0] != a[3]) for s in (0, 1) for a in self.alphabet}


def integer_test_machine(self, source, values):
    if self.profile == 'descending': return values['seed']
    optional = values['may'] & ~values['must']
    if source == 'test-or': return values['seed'] | (optional & -optional)
    legal = [x for x in range(1 << values['width'])
             if x & values['must'] == values['must'] and not x & ~values['may']]
    return next((x for x in legal if x > values['seed']), legal[0])


class TargetFiniteKernelTests(unittest.TestCase):
    def setUp(self):
        asc = ModuleType('research.observations.ascending_kernel')
        asc.ALPHABET = ('000', '010', '011', '111')
        asc.Runner = TestAscendingRunner
        desc = ModuleType('research.observations.source_factor')
        desc.Runner = TestDescendingRunner
        modules = patch.dict(sys.modules, {asc.__name__: asc, desc.__name__: desc})
        modules.start(); self.addCleanup(modules.stop)
        numeric = patch.object(System, 'integer_output', integer_test_machine)
        numeric.start(); self.addCleanup(numeric.stop)
        self.asc = {'observations': {'blocks': [['q0'], ['q1']]}}
        self.desc = {'word': {'source_ir': {'comparison_word': 'arg1'}}}

    def make(self, source='test-successor', profile='ascending', claim='cyclic_successor', spec=None):
        model = self.asc if profile == 'ascending' else self.desc
        spec = template(profile, claim) if spec is None else spec
        proposal = synthesize(source, model, spec)
        self.assertEqual(proposal['status'], 'candidate')
        return source, model, spec, proposal['certificate']

    def test_declared_successor_machine_is_certified(self):
        args = self.make()
        result = check(*args)
        self.assertEqual(result['status'], 'certified')
        self.assertTrue(result['all_positive_payload_widths'])
        self.assertEqual(result['alphabet_columns'], 6)

    def test_declared_faulty_machine_has_concrete_wrap_witness(self):
        args = self.make(source='test-or')
        result = check(*args)
        self.assertEqual(result['status'], 'refuted')
        self.assertEqual(result['counterexample']['width'], 1)
        self.assertEqual(result['counterexample']['seed'], 1)
        self.assertEqual(result['counterexample']['output'], 1)

    def test_descending_graph_and_output_rejecting_sink(self):
        args = self.make('test-identity', 'descending', 'bound')
        result = check(*args)
        self.assertEqual(result['status'], 'certified')
        self.assertEqual(result['alphabet_columns'], 32)
        self.assertTrue(result['source_rejecting_sink'])
        args = self.make('test-identity', 'descending', 'maximum')
        result = check(*args)
        self.assertEqual(result['status'], 'refuted')
        v = result['counterexample']
        self.assertLess(v['output'], v['alternative'])
        self.assertLessEqual(v['alternative'], v['bound'])

    def test_positive_width_does_not_impose_empty_word_obligation(self):
        spec = template('ascending', 'membership')
        spec['obligations'] = [['ne', 'ones', 'zero']]
        args = self.make(spec=spec)
        self.assertEqual(check(*args)['status'], 'certified')
        self.assertFalse(args[-1]['states'][0]['state'][1])

    def test_empty_observation_family_and_conditional_vacuity_are_explicit(self):
        spec = template('ascending', 'membership')
        spec['obligations'] = [True]
        args = self.make(spec=spec)
        result = check(*args)
        self.assertEqual(result['status'], 'certified')
        self.assertEqual(result['observations'], 0)
        spec['preconditions'] = [False]
        spec['obligations'] = [False]
        args = self.make(spec=spec)
        result = check(*args)
        self.assertEqual(result['status'], 'certified')
        self.assertEqual(result['preconditions'], [False])
        self.assertEqual(result['assumption_satisfiability'], 'not certified')

    def test_new_changes_formula_does_not_need_a_new_checker(self):
        self.assertEqual(check(*self.make(claim='changes'))['status'], 'certified')
        self.assertEqual(check(*self.make(source='test-or', claim='changes'))['status'], 'refuted')

    def test_recompiled_goal_program_not_trusted_from_certificate(self):
        args = self.make()
        for mutate in (
            lambda c: c['program']['atoms'].pop(),
            lambda c: c['program']['atoms'][0].update(left='output'),
            lambda c: c['program'].update(obligations=[True]),
            lambda c: c['program'].update(preconditions=[False]),
            lambda c: c['program'].update(quantifier='exists'),
        ):
            cert = deepcopy(args[-1]); mutate(cert)
            with self.assertRaisesRegex(ValueError, 'recompiled'): check(*args[:-1], cert)

    def test_positive_certificate_types_reachability_and_closure(self):
        args = self.make()
        for mutate in (
            lambda c: c.update(states=[]),
            lambda c: c['states'].pop(),
            lambda c: c['states'].append(deepcopy(c['states'][0])),
            lambda c: c['states'][0].update(parent=[0, '0000']),
            lambda c: c['states'][0]['state'].__setitem__(0, True),
            lambda c: c['states'][0]['state'].__setitem__(1, 0),
            lambda c: c['states'][0]['state'].__setitem__(2, 1),
            lambda c: c['states'][0]['state'].__setitem__(5, 0.0),
            lambda c: c['states'][1].update(parent=[1, '0000']),
            lambda c: c['states'][1].update(parent=[0, '0001']),
            lambda c: c.update(extra='ignored'),
        ):
            cert = deepcopy(args[-1]); mutate(cert)
            with self.assertRaises((ValueError, TypeError)): check(*args[:-1], cert)

    def test_rehashed_weaker_goal_cannot_prove_stronger_formula(self):
        args = self.make(source='test-or', claim='membership')
        stronger = template('ascending', 'cyclic_successor')
        cert = deepcopy(args[-1])
        cert['binding']['specification_sha256'] = digest(stronger)
        cert['program'] = compile_spec(stronger)
        with self.assertRaises(ValueError): check(args[0], args[1], stronger, cert)

    def test_counterexample_corruptions(self):
        args = self.make(source='test-or')
        for mutate in (
            lambda c: c.update(word=[]), lambda c: c.update(word=['0001']),
            lambda c: c.update(word=['0110'] * 257), lambda c: c.update(reason='obligation_0'),
            lambda c: c['values'].update(output=0), lambda c: c['values'].update(alternative=1),
            lambda c: c['binding'].update(source_sha256='0' * 64),
            lambda c: c.update(kind='closed_observation'),
        ):
            cert = deepcopy(args[-1]); mutate(cert)
            with self.assertRaises((ValueError, TypeError)): check(*args[:-1], cert)

    def test_direct_integer_execution_and_target_are_actually_used(self):
        args = self.make(source='test-or')
        with patch.object(System, 'integer_output', return_value=-1):
            with self.assertRaisesRegex(ValueError, 'integer source'): check(*args)
        with patch('research.observations.target_kernel.concrete_violation', return_value=None):
            with self.assertRaisesRegex(ValueError, 'integer target'): check(*args)

    def test_exhaustion_has_no_certificate(self):
        spec = template('ascending', 'cyclic_successor')
        result = synthesize('test-successor', self.asc, spec, max_states=1)
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertIsNone(result['certificate'])
        for bad in (0, True, 8193):
            with self.assertRaises(ValueError): synthesize('test-successor', self.asc, spec, max_states=bad)


if __name__ == '__main__': unittest.main()
