"""Boolean literals must survive compilation, including zero-atom targets."""
from copy import deepcopy
from itertools import product
import unittest

from research.observations.target_rules import (
    advance, columns, compile_spec, concrete_formula, initial, observed, violation,
)
from research.observations.target_templates import template


class TargetLiteralTests(unittest.TestCase):
    def test_compiled_literals_remain_booleans(self):
        for value in (False, True):
            spec = template('ascending', 'membership')
            spec.update(preconditions=[value], obligations=[value])
            program = compile_spec(spec)
            self.assertEqual(program['atoms'], [])
            self.assertIs(program['preconditions'][0], value)
            self.assertIs(program['obligations'][0], value)

    def test_nested_literals_agree_with_independent_integer_semantics(self):
        base = template('ascending', 'membership')
        atom = ['eq', 'output', 'seed']
        formulas = [False, True, ['not', False], ['not', True]]
        for connective in ('and', 'or', 'implies'):
            for left, right in product((False, True, atom), repeat=2):
                formulas.append([connective, deepcopy(left), deepcopy(right)])
        for expr in formulas:
            spec = {**base, 'preconditions': [], 'obligations': [expr]}
            program = compile_spec(spec)
            for column, output in product(columns('ascending'), (0, 1)):
                env = dict(zip(('must', 'may', 'seed', 'alternative'), map(int, column)))
                env['output'] = output
                state = advance(program, initial(program), env)
                expected = concrete_formula(expr, {'width': 1, **env})
                self.assertIs(observed(program['obligations'][0], state), expected)
                self.assertEqual(violation(program, state), None if expected else 'obligation_0')


if __name__ == '__main__':
    unittest.main()
