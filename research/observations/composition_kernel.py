"""Replay modular source-to-target certificates for the masked-ceiling wrapper.

A positive proof checks the TWO exact region properties first, then every weak
order of wrapper values and an independent masked competitor. A negative proof
has no assumption that the region properties hold: it checks region models,
executes the wrapper through both source interpreters and factors, and checks
a concrete target violation. No search, solver or native execution is imported.
"""
import hashlib
from collections import Counter

from .composition_execution import Execution
from .composition_order import domain_orders, evaluate, weak_orders
from .composition_program import inspect
from .composition_spec import (ROLES, RULES, check_spec, concrete_violation,
                                dependency_spec)
from .model import digest, integer, require
from .run_package import check_package

SCHEMA = 'qkf-masked-ceiling-composition-v1'
MAX_WITNESS_WIDTH = 256


def source_bindings(sources):
    require(type(sources) is dict and set(sources) == set(ROLES), 'two externally supplied region sources')
    require(all(type(v) is str for v in sources.values()), 'region source text')
    return {role: hashlib.sha256(sources[role].encode('utf-8')).hexdigest() for role in ROLES}


def binding(program, sources, spec):
    inspect(program)
    check_spec(spec)
    return {'program_sha256': digest(program), 'sources_sha256': source_bindings(sources),
            'specification_sha256': digest(spec), 'rules': RULES}


def checked_dependencies(sources, dependencies):
    require(type(dependencies) is dict and set(dependencies) == set(ROLES), 'both strong region dependencies')
    results = {}
    for role in ROLES:
        # The certificate cannot choose a weaker formula or introduce premises.
        results[role] = check_package(sources[role], dependency_spec(role), dependencies[role], profile=role)
        require(results[role]['status'] == 'certified', 'strong ' + role + ' contract must be certified')
    return results


def _scope():
    return {
        'claim': 'masked_ceiling',
        'semantics': 'typed JSON wrapper over the two restricted unsigned mathematical regions',
        'result': 'tagged Value(y) or Empty, never an untyped sentinel',
        'trusted': ['restricted source frontends and slice rules', 'typed target rules',
                    'mask extrema and seed-to-mask carrier identity',
                    'wrapper interpreter and weak-order composition rules'],
        'whole_computeLowerBound_or_create': False, 'native_java_all_widths': False,
        'new_lean_theorem': False, 'weak_order_realizability': 'overapproximation; not asserted',
    }


def check(program, sources, spec, certificate):
    expected_binding = binding(program, sources, spec)
    require(type(certificate) is dict and certificate.get('schema') == SCHEMA
            and certificate.get('kind') in {'weak_order_composition', 'counterexample'},
            'composition certificate kind')
    require(digest(certificate.get('binding')) == digest(expected_binding), 'composition source/program/goal binding')
    common = {'schema', 'kind', 'binding'}
    if certificate['kind'] == 'counterexample':
        require(set(certificate) == common | {'models', 'models_sha256', 'input', 'alternative', 'execution', 'reason'},
                'composition counterexample fields')
        require(digest(certificate['models']) == certificate['models_sha256'], 'counterexample model identities')
        inputs = certificate['input']
        require(type(inputs) is dict and integer(inputs.get('width'), 1, MAX_WITNESS_WIDTH), 'witness width limit')
        execution = Execution(sources, certificate['models']).run(program, inputs, check_factor=True)
        require(digest(execution) == digest(certificate['execution']), 'concrete wrapper/source/factor trace agreement')
        reason = concrete_violation(spec, inputs, execution['result'], certificate['alternative'])
        require(reason is not None and reason == certificate['reason'], 'independent composition target violation')
        return {'status': 'refuted', **_scope(), 'all_positive_payload_widths': False,
                'reason': reason, 'counterexample': {'input': inputs, 'alternative': certificate['alternative'],
                                                   **execution},
                'checked_by': ['typed wrapper execution', 'integer source regions',
                               'checked source factors', 'integer masked-ceiling target']}

    require(set(certificate) == common | {'dependencies', 'dependencies_sha256', 'names', 'cases'},
            'modular composition certificate fields')
    require(digest(certificate['dependencies']) == certificate['dependencies_sha256'], 'dependency package identities')
    checked = checked_dependencies(sources, certificate['dependencies'])
    names, orders = domain_orders(program)
    require(certificate['names'] == names, 'wrapper live-value interface')
    cases = certificate['cases']
    require(type(cases) is list and len(cases) == len(orders), 'complete weak-order case population')
    counts = Counter()
    for entry, ranks in zip(cases, orders):
        require(type(entry) is dict and set(entry) == {'order', 'result'}, 'weak-order proof row')
        require(type(entry['order']) is list and all(type(x) is int for x in entry['order'])
                and tuple(entry['order']) == ranks, 'canonical complete weak-order enumeration')
        result = evaluate(program, names, ranks)
        require(result['outcome'] != 'gap', 'composition obligation fails: ' + result.get('reason', 'unknown'))
        require(digest(entry['result']) == digest(result), 'recomputed weak-order derivation')
        counts[result['outcome']] += 1
    return {'status': 'certified', **_scope(), 'all_positive_payload_widths': True,
            'specification_sha256': digest(spec), 'program_sha256': digest(program),
            'preconditions': spec['preconditions'], 'obligations': spec['obligations'],
            'order_labels': len(names), 'all_weak_orders': len(weak_orders(len(names))),
            'checked_order_cases': len(orders), 'outcomes': dict(counts),
            'dependency_properties': {role: {'status': checked[role]['status'],
                'specification_sha256': digest(dependency_spec(role)),
                'source_claim': checked[role]['source_model']['claim']} for role in ROLES},
            'proof_basis': 'complete order cases + separately tracked membership + checked universal region contracts'}


def explain(program, sources, spec, certificate):
    result = check(program, sources, spec, certificate)
    return {**result, 'explanation': {
        'replayed': True,
        'chain': ['external region sources -> source factors',
                  'factors -> exact maximum and cyclic successor contracts',
                  'external wrapper -> call-entry and dataflow obligations',
                  'complete weak orders -> masked ceiling and exact emptiness']
                 if result['status'] == 'certified' else
                 ['external wrapper -> concrete region calls', 'source/factor agreement -> tagged result',
                  'independent legal competitor -> concrete target violation'],
        'key_handoff': 'a legal later successor also instantiates the earlier universal floor contract',
        'no_sentinel_inference': True,
    }}
