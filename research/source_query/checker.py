"""Standalone source-bound consumer verification; no producer imports."""
from research.ground_query.checker import check as check_ground
from research.ground_query.schema import fields, require, parse
from research.signed_predicates.frontend import target_value
from research.signed_predicates.semantics import evaluate
from .context import PROOF, prepare, snapshot, integer, MAX_WIDTH
from .encoding import Graph
from .rules import check_fact


def envelope(ctx, kind, evidence):
    return {'schema': PROOF, 'binding': ctx.binding(), 'kind': kind, 'evidence': evidence}


def witness(ctx, evidence):
    fields(evidence, ('width', 'input'), 'concrete witness')
    width = integer(evidence['width'], 1, MAX_WIDTH, 'witness width')
    require(ctx.width is None or width == ctx.width, 'witness outside requested width')
    raw = integer(evidence['input'], 0, (1 << width) - 1, 'witness input')
    sign = raw >> (width - 1)
    require(ctx.guard(raw.bit_count(), sign), 'counterexample violates G')
    actual = evaluate(ctx.ir, raw, width)
    expected = target_value(ctx.spec['target'], raw.bit_count(), sign)
    require(type(actual) is bool and actual != expected, 'word does not refute consumer')
    return {'width': width, 'input': raw, 'source_value': actual, 'target_value': expected,
            'guard_satisfied': True, 'java_executed': False}


def check(source, request, certificate):
    ctx = prepare(source, request)
    proof = snapshot(certificate)
    fields(proof, ('schema', 'binding', 'kind', 'evidence'), 'consumer proof')
    require(proof['schema'] == PROOF and proof['binding'] == ctx.binding(),
            'source/request/IR/ruleset binding')
    kind, evidence = proof['kind'], proof['evidence']
    require(type(kind) is str and kind in ('ground', 'empty', 'witness', 'covered'), 'consumer proof kind')
    base = {'schema': 'qkf-guarded-source-result-v1', 'binding': ctx.binding(),
            'width': ctx.request['width'], 'guards': ctx.guards,
            'claim': 'G implies source equals the independently supplied target',
            'conditional': bool(ctx.guards), 'lean_checked': False,
            'scope': 'retained modular signed semantics; trusted frontend, native rule schemas, target semantics and Python proof checkers'}
    if kind == 'empty':
        fields(evidence, (), 'empty-domain proof')
        require(not ctx.domain, 'G is not empty in the requested width scope')
        return {**base, 'status': 'verified_empty_domain', 'vacuous': True,
                'target_checked': True, 'all_positive_widths': ctx.width is None,
                'source_interface_verified': False}
    require(ctx.domain, 'use the explicit empty-domain result')
    if kind == 'witness':
        verified = witness(ctx, evidence)
        return {**base, 'status': 'refuted', 'target_checked': True,
                'all_positive_widths': False, 'witness': verified, 'source_interface_verified': False}
    if kind == 'covered':
        from .fallback import check_covered
        verified = check_covered(source, ctx, evidence)
        return {**base, 'status': 'certified', 'target_checked': True,
                'all_positive_widths': ctx.width is None, 'source_interface_verified': True,
                'fallback': verified}
    fields(evidence, ('facts', 'request', 'certificate'), 'native ground evidence')
    ground, facts = evidence['request'], evidence['facts']
    inp = parse(ground)
    g = Graph(ctx, ground)
    require(inp.queries == ((g.source(), g.target()),), 'ground query must be this source and target')
    require(type(facts) is list and len(facts) == len(inp.equations) <= 4096,
            'every ground axiom needs exactly one native proof')
    for fact, equation in zip(facts, inp.equations):
        require(check_fact(ctx, g, fact) == equation, 'native proof does not establish this axiom')
    checked = check_ground(ground, evidence['certificate'])
    require(checked['mode'] == 'entailment' and checked['horizon'] == inp.horizon,
            'consumer proof uses ordinary entailment at the complete finite horizon')
    equal = checked['goals'][0]['status'] == 'equal'
    return {**base, 'status': 'certified' if equal else 'unresolved', 'target_checked': equal,
            'all_positive_widths': equal and ctx.width is None,
            'source_refutation': False, 'abstract_nonconsequence': not equal,
            'source_interface_verified': False, 'checked_native_facts': len(facts),
            'ground_terms': len(inp.nodes), 'ground_result': checked}
