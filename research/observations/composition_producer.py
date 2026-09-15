"""Bounded composition proof production; the checker never imports this module.

Failure of a dependency or an abstract order case is NOT a program refutation.
Only a feasible whole-program input, checked independently, yields a negative
certificate. Otherwise report unresolved or budget exhaustion without a proof.
"""
from .composition_execution import CallDomainError, Execution
from .composition_kernel import SCHEMA, binding, check
from .composition_order import MAX_ORDERS, domain_orders, evaluate
from .composition_program import inspect
from .composition_spec import ROLES, concrete_violation, dependency_spec
from .model import digest, integer, require
from .run_package import check_package


def bounded_inputs(max_width):
    for width in range(1, max_width + 1):
        for may in range(1 << width):
            must = may
            submasks = []
            while True:
                submasks.append(must)
                if must == 0:
                    break
                must = (must - 1) & may
            for must in reversed(submasks):
                for bound in range(1 << width):
                    yield {'width': width, 'bound': bound, 'must': must, 'may': may}


def find_counterexample(program, sources, spec, models, *, max_width=5, max_inputs=20000):
    require(integer(max_width, 1, 8) and integer(max_inputs, 0, 1000000), 'bounded refutation search budget')
    runner = Execution(sources, models)
    checked, outside = 0, 0
    for inputs in bounded_inputs(max_width):
        if checked == max_inputs:
            return None, {'tested_inputs': checked, 'out_of_contract_calls': outside, 'exhausted': True}
        checked += 1
        try:
            execution = runner.run(program, inputs, check_factor=False)
        except CallDomainError:
            outside += 1
            continue
        m, a, b = (inputs[k] for k in ('must', 'may', 'bound'))
        expected = next((z for z in range(b, 1 << inputs['width'])
                         if z & m == m and not z & ~a), None)
        alternative = a if expected is None else expected
        reason = concrete_violation(spec, inputs, execution['result'], alternative)
        if reason is not None:
            certificate = {'schema': SCHEMA, 'kind': 'counterexample', 'binding': binding(program, sources, spec),
                           'models': models, 'models_sha256': digest(models), 'input': inputs,
                           'alternative': alternative, 'execution': execution, 'reason': reason}
            check(program, sources, spec, certificate)
            return certificate, {'tested_inputs': checked, 'out_of_contract_calls': outside, 'exhausted': False}
    return None, {'tested_inputs': checked, 'out_of_contract_calls': outside, 'exhausted': False}


def synthesize(program, sources, spec, *, dependencies=None, max_orders=MAX_ORDERS,
               max_witness_width=5, max_inputs=20000):
    require(integer(max_orders, 1, MAX_ORDERS) and integer(max_witness_width, 1, 8)
            and integer(max_inputs, 0, 1000000), 'composition search budgets')
    base = {'schema': SCHEMA, 'binding': binding(program, sources, spec)}
    inspect(program)
    if dependencies is None:
        from .run_producer import verify
        dependencies = {}
        for role in ROLES:
            result, package = verify(sources[role], dependency_spec(role), profile=role)
            if package is None:
                return {'status': result['status'], 'stage': role + '_dependency',
                        'detail': result, 'certificate': None}
            dependencies[role] = package
    require(type(dependencies) is dict and set(dependencies) == set(ROLES), 'two supplied dependencies')
    dependency_results = {role: check_package(sources[role], dependency_spec(role), dependencies[role], profile=role)
                          for role in ROLES}
    models = {role: dependencies[role]['proofs']['source'] for role in ROLES}
    gap = None
    if all(result['status'] == 'certified' for result in dependency_results.values()):
        names, orders = domain_orders(program)
        if len(orders) > max_orders:
            return {'status': 'budget_exhausted', 'stage': 'composition_orders',
                    'required_order_cases': len(orders), 'certificate': None}
        cases = []
        for ranks in orders:
            result = evaluate(program, names, ranks)
            if result['outcome'] == 'gap':
                gap = {'kind': 'abstract_obligation', 'names': names, 'order': list(ranks), **result}
                break
            cases.append({'order': list(ranks), 'result': result})
        if gap is None:
            certificate = {**base, 'kind': 'weak_order_composition', 'dependencies': dependencies,
                           'dependencies_sha256': digest(dependencies), 'names': names, 'cases': cases}
            check(program, sources, spec, certificate)
            return {'status': 'candidate', 'certificate': certificate}
    else:
        gap = {'kind': 'dependency_not_certified',
               'statuses': {k: v['status'] for k, v in dependency_results.items()}}
    certificate, search = find_counterexample(program, sources, spec, models,
                                              max_width=max_witness_width, max_inputs=max_inputs)
    if certificate is not None:
        return {'status': 'candidate', 'certificate': certificate, 'search': search}
    return {'status': 'budget_exhausted' if search['exhausted'] else 'unresolved',
            'stage': 'composition_obligation', 'diagnostic': gap, 'search': search,
            'reason': 'no universal composition proof and no checked concrete refutation', 'certificate': None}
