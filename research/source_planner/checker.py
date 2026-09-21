"""Independent bounded source-ground consumer verification, without planning."""
from research.ground_query.schema import fields, parse
from research.ground_query.checker import check as check_ground
from research.source_query.encoding import Graph
from research.source_query.rules import check_fact
from .context import RULESET, prepare, snapshot, require, integer


def native_input(ctx, evidence):
    inp = parse(evidence['request'])
    g = Graph(ctx, evidence['request'])
    require(inp.queries == ((g.source(), g.target()),), 'actual independent source/consumer roots')
    facts = evidence['facts']
    require(type(facts) is list and len(facts) == len(inp.equations) <= 4096, 'every E axiom needs a native proof')
    for fact, equation in zip(facts, inp.equations):
        require(check_fact(ctx, g, fact) == equation, 'source fact does not justify E')
    return inp


def check(source, request, raw_certificate):
    ctx, cert = prepare(source, request), snapshot(raw_certificate)
    fields(cert, ('schema', 'binding', 'kind', 'evidence'), 'planner consumer proof')
    require(cert['schema'] == 'qkf-source-plan-proof-v1' and cert['binding'] ==
            dict(source=ctx.binding(), checker_ruleset=RULESET), 'source/request/IR/guard/width binding')
    base = dict(schema='qkf-source-plan-result-v1', binding=cert['binding'],
                width=ctx.request['width'], guards=ctx.guards, lean_checked=False,
                scope='retained guarded modular signed semantics; bounded native vocabulary and Python checkers')
    kind, evidence = cert['kind'], cert['evidence']
    if kind == 'legacy':
        fields(evidence, ('proof',), 'retained source proof')
        from research.source_query.checker import check as retained_check
        proof = evidence['proof']
        require(type(proof) is dict and proof.get('kind') in ('empty', 'witness', 'covered'), 'retained proof kind')
        verified = retained_check(source, request, proof)
        return dict(base, status=verified['status'], reason={
                    'empty': 'empty_guard', 'witness': 'concrete_violation',
                    'covered': 'explicit_covered_fallback'}[proof['kind']],
                    target_checked=verified['target_checked'], source_result=verified)
    require(kind in ('ground', 'inactive'), 'source plan proof kind')
    fields(evidence, ('request', 'facts', 'certificate' if kind == 'ground' else 'horizon'), 'native ground evidence')
    require(ctx.domain, 'empty domain needs explicit retained empty proof')
    inp = native_input(ctx, evidence)
    if kind == 'inactive':
        horizon = integer(evidence['horizon'], 0, 128, 'activation ceiling')
        require(any(max(inp.depths[a], inp.depths[b]) > horizon for a, b in inp.queries), 'query is active')
        return dict(base, status='unresolved', reason='insufficient_horizon', target_checked=False,
                    ground_relation='inactive_query', horizon=horizon,
                    required_horizon=max(inp.depths[x] for pair in inp.queries for x in pair),
                    final_horizon=inp.horizon,
                    source_refutation=False, checked_native_facts=len(inp.equations))
    verified = check_ground(evidence['request'], evidence['certificate'])
    require(verified['mode'] == 'entailment', 'consumer needs entailment, not an exact-threshold claim')
    relation = verified['goals'][0]['status']
    equal = relation == 'equal'
    return dict(base, status='certified' if equal else 'unresolved', target_checked=equal,
                reason='consumer_closed' if equal else 'insufficient_horizon' if relation == 'not_visible'
                else 'not_entailed_from_current_E', ground_relation=relation,
                all_positive_widths=equal and ctx.width is None, source_refutation=False,
                checked_native_facts=len(inp.equations), ground_terms=len(inp.nodes), ground_result=verified)
