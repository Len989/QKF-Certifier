"""Source-independent tests of order completeness, membership and composition syntax."""
from collections import Counter
from copy import deepcopy
from itertools import product
import unittest

from research.observations.composition_order import domain_orders, evaluate, weak_orders
from research.observations.composition_program import execute, inspect, program, variants
from research.observations.composition_spec import (concrete_violation, dependency_spec,
                                                   specification, validate_input)
from research.observations.target_templates import template


class CompositionOrderTests(unittest.TestCase):
    def test_weak_orders_are_all_total_preorders_once(self):
        self.assertEqual([len(weak_orders(i)) for i in range(1, 7)], [1, 3, 13, 75, 541, 4683])
        for size in range(1, 5):
            reference = set()
            for values in product(range(size), repeat=size):
                labels = {v: i for i, v in enumerate(sorted(set(values)))}
                reference.add(tuple(labels[v] for v in values))
            self.assertEqual(set(weak_orders(size)), reference)
        self.assertEqual(len(set(weak_orders(6))), 4683)
        for ranks in weak_orders(6):
            self.assertEqual(set(ranks), set(range(max(ranks) + 1)))

    def test_example_proves_every_admitted_order(self):
        p = program()
        names, orders = domain_orders(p)
        self.assertEqual(names, ['bound', 'must', 'may', 'floor', 'next', 'alternative'])
        self.assertEqual(len(orders), 1076)
        counts = Counter(evaluate(p, names, r)['outcome'] for r in orders)
        self.assertEqual(counts, {'value': 328, 'empty': 236, 'contract_eliminated': 512})

    def test_new_successor_membership_reinstantiates_old_floor_contract(self):
        p = program()
        names, _ = domain_orders(p)
        # must=0, floor=0, next=1, bound=2, may=3, alternative=3.
        # Floor is initially possible for the known legal endpoints and z.
        # next becomes legal only after the call, contradicting maximality.
        ranks = [2, 0, 3, 0, 1, 3]
        result = evaluate(p, names, ranks)
        self.assertEqual(result['outcome'], 'contract_eliminated')
        self.assertTrue(result['path'].endswith('then.no'))
        self.assertEqual(result['trace'][-1][1], 'ascending')

    def test_mask_carrier_identity_at_seed_must_is_coordinatewise(self):
        for m, a in ((0, 0), (0, 1), (1, 1)):
            optional = a & (1 - m)
            self.assertEqual(m & optional, 0)
            generated = {m | s for s in (0, 1) if not s & (1 - optional)}
            self.assertEqual(generated, {x for x in (0, 1) if m <= x <= a})

    def test_dependency_formulas_match_exact_run2_contracts(self):
        for role, claim in [('ascending', 'cyclic_successor'), ('descending', 'maximum')]:
            self.assertEqual(dependency_spec(role), template(role, claim))
            self.assertNotEqual(dependency_spec(role), template(role, 'membership' if role == 'ascending' else 'bound'))

    def test_mutated_wrapper_has_gap_not_an_abstract_refutation(self):
        for name, p in variants().items():
            names, orders = domain_orders(p)
            gaps = [evaluate(p, names, r) for r in orders if evaluate(p, names, r)['outcome'] == 'gap']
            self.assertEqual(bool(gaps), name not in {'original', 'inclusive_minimum'}, name)
            self.assertTrue(all('input' not in g and 'counterexample' not in g for g in gaps))

    def test_syntax_rejects_paths_arbitrary_code_cycles_and_future_reads(self):
        modifications = [
            lambda p: p.update(schema='wrong'), lambda p: p.update(assumptions=[True]),
            lambda p: p['entry'].update(op='eval'),
            lambda p: p['entry']['yes'].update(word='floor'),
            lambda p: p['entry']['yes'].update(word='alternative'),
            lambda p: p['entry']['yes'].update(word=0),
            lambda p: p['entry']['no']['yes'].update(value=-1),
            lambda p: p['entry']['no']['no'].update(role='path/to/code'),
            lambda p: p['entry']['no']['no'].update(bind='must'),
            lambda p: p['entry']['no']['no']['args'].update(seed='floor'),
            lambda p: p['entry']['no']['no']['then']['no'].update(role='descending'),
            lambda p: p['entry']['no']['no']['then']['no'].update(bind='floor'),
            lambda p: p['entry'].update(test=['ult', 'bound']),
        ]
        for mutate in modifications:
            p = program()
            mutate(p)
            with self.assertRaises(ValueError): inspect(p)
        p = program()
        p['entry']['no'] = p['entry']
        with self.assertRaises(ValueError): inspect(p)

    def test_numeric_interval_does_not_imply_mask_membership(self):
        p={'schema':program()['schema'],'entry':{'op':'value','word':'bound'}}
        names,_=domain_orders(p)
        # must < bound < may, and z=must: bound can be outside the mask.
        result=evaluate(p,names,[1,0,2,0])
        self.assertEqual(result['outcome'],'gap')
        self.assertEqual(result['reason'],'result_membership_not_established')

    def test_reordered_guards_do_not_require_the_template_tree(self):
        p=program()
        lower=p['entry']; upper=lower['no']
        p['entry']={'op':'if','test':upper['test'],'yes':upper['yes'],
                    'no':{'op':'if','test':lower['test'],'yes':lower['yes'],'no':upper['no']}}
        names,orders=domain_orders(p)
        self.assertTrue(all(evaluate(p,names,r)['outcome']!='gap' for r in orders))

    def test_name_renaming_does_not_change_proof(self):
        p = program()
        def rename(x):
            if isinstance(x, dict): return {k: rename(v) for k, v in x.items()}
            if isinstance(x, list): return [rename(v) for v in x]
            return {'floor': 'g0', 'next': 'successor_result'}.get(x, x) if isinstance(x, str) else x
        p = rename(p)
        names, orders = domain_orders(p)
        self.assertTrue(all(evaluate(p, names, r)['outcome'] != 'gap' for r in orders))

    def test_numeric_target_controls_and_result_tags(self):
        s = specification()
        v = dict(width=3, must=0, may=5, bound=2)
        self.assertIsNone(concrete_violation(s, v, {'kind':'value','value':4}, 4))
        self.assertEqual(concrete_violation(s, v, {'kind':'empty'}, 4), 'empty_with_feasible_value')
        self.assertEqual(concrete_violation(s, v, {'kind':'value','value':1}, 4), 'below_bound')
        self.assertEqual(concrete_violation(s, v, {'kind':'value','value':5}, 4), 'not_minimal')
        self.assertEqual(concrete_violation(s, v, {'kind':'value','value':2}, 4), 'output_outside_mask')
        for result in ({'kind':'empty','value':0}, {'kind':'value','value':True},
                       {'kind':'value','value':-1}, {'kind':'value','value':8}):
            with self.assertRaises(ValueError): concrete_violation(s,v,result,4)
        for change in ({'width':0}, {'width':True}, {'must':2,'may':1}, {'bound':8}):
            with self.assertRaises(ValueError): validate_input({**v,**change})

    def test_goal_cannot_weaken_and_unused_call_results_are_not_read(self):
        changed = specification()
        changed['obligations'].pop()
        with self.assertRaises(ValueError):
            concrete_violation(changed,dict(width=1,must=0,may=0,bound=0),{'kind':'value','value':0},0)
        def forbidden(*args): raise AssertionError('unexpected call')
        output = execute(program(),dict(width=2,must=2,may=3,bound=0),forbidden)
        self.assertEqual(output['result'],{'kind':'value','value':2})
        output = execute(program(),dict(width=2,must=0,may=1,bound=3),forbidden)
        self.assertEqual(output['result'],{'kind':'empty'})


if __name__ == '__main__': unittest.main()
