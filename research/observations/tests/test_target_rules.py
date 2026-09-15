"""Numerical controls for typed formula compilation, independent of source code."""
from copy import deepcopy
from itertools import product
import random
import unittest

from research.observations.target_rules import (
    COLUMN_NAMES, advance, bit_value, columns, compile_spec, concrete_formula,
    concrete_violation, initial, valid_state, violation, word_value,
)
from research.observations.target_templates import template


class TargetRulesTests(unittest.TestCase):
    def test_alphabet_never_assumes_output_legality(self):
        self.assertEqual(len(columns('ascending')), 6)
        self.assertEqual(len(columns('descending')), 32)
        groups = {}
        for column in columns('descending'):
            key = column[:4] + column[5]
            groups.setdefault(key, set()).add(column[4])
        self.assertTrue(groups)
        self.assertTrue(all(v == {'0', '1'} for v in groups.values()))
        self.assertEqual({c[2:] for c in columns('ascending') if c[:2] == '01'},
                         {'00', '01', '10', '11'})

    def test_monitor_matches_integer_formula_exhaustively(self):
        comparisons = 0
        for profile, claims, maximum_width in (
            ('ascending', ('cyclic_successor', 'membership', 'changes'), 3),
            ('descending', ('maximum', 'bound'), 2),
        ):
            specs = [template(profile, claim) for claim in claims]
            programs = [compile_spec(spec) for spec in specs]
            for width in range(1, maximum_width + 1):
                for word in product(columns(profile), repeat=width):
                    outputs = product((0, 1), repeat=width) if profile == 'ascending' else [None]
                    for ys in outputs:
                        envs = [dict(zip(COLUMN_NAMES[profile], map(int, c))) for c in word]
                        if ys is not None:
                            for env, y in zip(envs, ys): env['output'] = y
                        values = {'width': width, **{k: sum(e[k] << i for i, e in enumerate(envs))
                                                   for k in envs[0]}}
                        for spec, program in zip(specs, programs):
                            state = initial(program)
                            for env in envs: state = advance(program, state, env)
                            self.assertTrue(valid_state(program, state))
                            self.assertEqual(violation(program, state), concrete_violation(spec, values))
                            comparisons += 1
        self.assertEqual(comparisons, 7764)

    def test_exact_quantified_cyclic_target_against_numeric_successor(self):
        spec = template('ascending', 'cyclic_successor')
        checked = 0
        for width in range(1, 4):
            for must, may, seed in product(range(1 << width), repeat=3):
                if seed & must != must or seed & ~may: continue
                legal = [z for z in range(1 << width) if z & must == must and not z & ~may]
                expected = next((z for z in legal if z > seed), legal[0])
                for output in range(1 << width):
                    accepted = all(concrete_violation(spec, dict(width=width, must=must, may=may,
                        seed=seed, output=output, alternative=z)) is None for z in legal)
                    self.assertEqual(accepted, output == expected)
                    checked += 1
        self.assertEqual(checked, 584)

    def test_exact_quantified_maximum_contract_with_arbitrary_raw_masks(self):
        specs = [template('descending', c) for c in ('maximum', 'bound')]
        for width in range(1, 3):
            for bound, must, may, seed in product(range(1 << width), repeat=4):
                optional = may & ~must
                if seed & optional or seed > bound: continue
                legal = [z for z in range(1 << width)
                         if z & seed == seed and not z & ~(seed | optional)]
                feasible = [z for z in legal if z <= bound]
                for output in range(1 << width):
                    for spec, expected in zip(specs, (output == max(feasible), output in feasible)):
                        accepted = all(concrete_violation(spec, dict(width=width, bound=bound,
                            must=must, may=may, seed=seed, output=output, alternative=z)) is None for z in legal)
                        self.assertEqual(accepted, expected)

    def test_observations_follow_formula_and_share_repeated_order_questions(self):
        spec = template('ascending', 'membership')
        self.assertEqual(len(compile_spec(spec)['atoms']), 2)
        spec['obligations'] = [['or', ['ult', 'seed', 'output'], ['ule', 'seed', 'output'],
                                ['uge', 'output', 'seed']]]
        self.assertEqual(len(compile_spec(spec)['atoms']), 1)
        spec['obligations'] = [True]
        self.assertEqual(compile_spec(spec)['atoms'], [])

    def test_boolean_and_word_expression_semantics_at_wide_widths(self):
        rng = random.Random(15092026)
        spec = template('descending', 'maximum')
        words = ['seed', 'output', 'alternative', 'zero', 'ones',
                 ['bit_not', 'may'], ['bit_xor', 'seed', 'alternative'],
                 ['bit_or', ['bit_and', 'may', 'output'], ['bit_not', 'must']]]
        predicates = ['eq', 'ne', 'ult', 'ule', 'ugt', 'uge', 'subset', 'disjoint']
        for sample in range(120):
            width = [1, 64, 257, 1024][sample % 4]
            mask = (1 << width) - 1
            must, may, raw = (rng.getrandbits(width) for _ in range(3))
            optional = may & ~must
            seed = raw & ~optional
            alternative = seed | (rng.getrandbits(width) & optional)
            values = dict(width=width, bound=rng.getrandbits(width), must=must, may=may,
                          seed=seed, alternative=alternative, output=rng.getrandbits(width))
            p = [rng.choice(predicates), deepcopy(rng.choice(words)), deepcopy(rng.choice(words))]
            q = [rng.choice(predicates), deepcopy(rng.choice(words)), deepcopy(rng.choice(words))]
            spec['preconditions'] = []
            spec['obligations'] = [['and', ['or', p, ['not', q]], ['implies', p, q]]]
            program = compile_spec(spec)
            state = initial(program)
            reconstructed = [0] * len(words)
            for i in range(width):
                env = {k: (v >> i) & 1 for k, v in values.items() if k != 'width'}
                state = advance(program, state, env)
                for j, word in enumerate(words): reconstructed[j] |= bit_value(word, env) << i
            self.assertEqual(reconstructed, [word_value(w, values, mask) for w in words])
            self.assertEqual(violation(program, state), concrete_violation(spec, values))
            self.assertEqual(violation(program, state) is None, concrete_formula(spec['obligations'][0], values))

    def test_invalid_specs_and_hidden_output_assumptions(self):
        good = template('ascending', 'cyclic_successor')
        mutations = [
            lambda s: s.update(schema='unknown'), lambda s: s.update(profile=[]),
            lambda s: s.update(domain='all Java'), lambda s: s.update(quantifier='exists'),
            lambda s: s.update(extra='code'), lambda s: s.update(obligations=[]),
            lambda s: s.update(obligations=[1]), lambda s: s.update(obligations=[['and', True]]),
            lambda s: s.update(obligations=[['eq', True, 'seed']]),
            lambda s: s.update(obligations=[['ult', 'bound', 'seed']]),
            lambda s: s.update(obligations=[['eq', ['add', 'seed', 'ones'], 'output']]),
            lambda s: s.update(preconditions=[['subset', 'output', 'may']]),
            lambda s: s.update(preconditions=[['eq', ['bit_and', 'alternative', 'may'], 'zero']]),
            lambda s: s.update(obligations=[['forall', 'output', True]]),
        ]
        for mutation in mutations:
            altered = deepcopy(good); mutation(altered)
            with self.assertRaises((ValueError, TypeError)): compile_spec(altered)

    def test_syntax_depth_size_and_observation_budgets(self):
        spec = template('ascending', 'membership')
        formula = True
        for _ in range(18): formula = ['not', formula]
        spec['obligations'] = [formula]
        with self.assertRaises(ValueError): compile_spec(spec)
        spec['obligations'] = [['and', *([['and', *([True] * 16)]] * 16)]] * 3
        with self.assertRaises(ValueError): compile_spec(spec)
        spec['obligations'] = [['and', *([['eq', a, b] for a in ('must', 'may', 'seed', 'output')
                                         for b in ('must', 'may', 'seed', 'output')])],
                               ['eq', 'alternative', 'zero']]
        with self.assertRaisesRegex(ValueError, 'observation budget'): compile_spec(spec)

    def test_boolean_and_order_state_types_are_not_interchangeable(self):
        program = compile_spec(template('ascending', 'cyclic_successor'))
        state = list(initial(program))
        for i, atom in enumerate(program['atoms']):
            changed = state[:]
            changed[i] = True if atom['kind'] == 'order' else 1
            self.assertFalse(valid_state(program, changed))
        self.assertFalse(valid_state(program, state[:-1]))

    def test_invalid_concrete_values_and_competitor_domain(self):
        spec = template('ascending', 'membership')
        good = dict(width=2, must=1, may=3, seed=1, output=3, alternative=1)
        for key, value in [('width', 0), ('width', True), ('output', True), ('output', 4),
                           ('seed', 0), ('alternative', 0)]:
            with self.assertRaises(ValueError): concrete_violation(spec, {**good, key: value})
        self.assertIsNotNone(concrete_violation(spec, {**good, 'output': 0}))


if __name__ == '__main__': unittest.main()
