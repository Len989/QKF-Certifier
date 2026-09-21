"""Versioned requests and strict, source-free consumer admission."""
from research.semantic_work.contract import canonical, digest, snapshot, load_json, save_json
from research.ground_query.schema import fields, require
from research.source_query.context import integer, target_domain
from research.signed_predicates.frontend import CONTRACT as SIGNED, goal, target_value
from research.unified.v3_schema import compile_target, SIGNED_KIND
from research.signed_bridge.model import request as selection
from research.wordexpr.frontend import Unsupported

REQUEST = 'qkf-summary-request-v1'
PACKET = 'qkf-applicable-summary-v1'
RESULT = 'qkf-summary-result-v1'
PHASE = 'graal-ascending-physical-phases-v1'
CAP = 4


def signed_spec(q):
    fields(q, ('schema', 'target', 'guards', 'width'), 'signed query')
    require(q['schema'] == 'qkf-guarded-source-query-v1', 'signed query schema')
    require(type(q['target']) is dict and q['target'].get('schema') == 'qkf-target-v2', 'target v2')
    compiled = compile_target(q['target'])
    require(compiled['kind'] == SIGNED_KIND, 'signed Boolean target')
    spec = compiled['specification']
    require(type(q['guards']) is list and len(q['guards']) <= 16, 'guard conjunction')
    caps = [goal(spec)] + [goal(dict(spec, target=g)) for g in q['guards']]
    if max(caps) > CAP:
        raise Unsupported('summary target/guard counts must be in 0..3')
    width = q['width']
    require(type(width) is dict, 'width scope')
    if width.get('kind') == 'all_positive':
        fields(width, ('kind',), 'all-positive width')
    else:
        fields(width, ('kind', 'bits'), 'fixed width')
        require(width['kind'] == 'fixed', 'width kind')
        integer(width['bits'], 1, 4096, 'fixed width 1..4096')
    return spec, selection(spec['entry'], spec['word_type'])


def request(raw):
    r = snapshot(raw)
    fields(r, ('schema', 'profile', 'query'), 'summary request')
    require(r['schema'] == REQUEST, 'summary request version')
    if r['profile'] == SIGNED:
        q = r['query']
        fields(q, ('schema', 'requests'), 'signed batch')
        require(q['schema'] == 'qkf-source-lemma-batch-v1' and type(q['requests']) is list
                and 0 < len(q['requests']) <= 64, 'signed independent requests')
        anchor = None
        for item in q['requests']:
            _, selected = signed_spec(item)
            scope = canonical([selected, item['guards'], item['width']])
            require(anchor is None or scope == anchor, 'one exact selection/guard/width per summary')
            anchor = scope
    elif r['profile'] == PHASE:
        q = r['query']
        fields(q, ('schema', 'profile', 'label', 'goals'), 'physical-phase request')
        require(q['schema'] == 'qkf-local-forcing-request-v1' and q['profile'] == PHASE, 'phase profile')
        require(type(q['label']) is list and len(q['label']) == 4, 'physical label')
        m, a, g, _ = [integer(v, 0, 1, 'label bit') for v in q['label']]
        require(m <= g <= a, 'admissible phase cell')
        require(type(q['goals']) is list and 0 < len(q['goals']) <= 16, 'phase goals')
        for pair in q['goals']:
            require(type(pair) is list and len(pair) == 2, 'phase input/claim')
            for v in pair:
                integer(v, 0, 7, 'phase subset')
    else:
        raise Unsupported('unknown summary semantic profile')
    return r


def signed_request(targets, *, guards=None, width=None):
    from research.source_query.context import make_request
    targets = [targets] if type(targets) is dict else targets
    require(type(targets) is list, 'independent target list')
    return request(dict(schema=REQUEST, profile=SIGNED, query=dict(
        schema='qkf-source-lemma-batch-v1', requests=[make_request(t, guards, width) for t in targets])))


def phase_request(label, goals):
    return request(dict(schema=REQUEST, profile=PHASE, query=dict(
        schema='qkf-local-forcing-request-v1', profile=PHASE, label=label, goals=goals)))


def status(goals):
    statuses = {g['status'] for g in goals}
    if 'refuted' in statuses:
        return 'refuted'
    if 'unresolved' in statuses:
        return 'unresolved'
    if statuses == {'verified_empty_domain'}:
        return 'verified_empty_domain'
    require(statuses <= {'certified', 'verified_empty_domain'} and statuses, 'checked goal statuses')
    return 'certified'


def interface(r, results):
    """Compile only a checked consumer's sufficient action, never source execution."""
    if r['profile'] == PHASE:
        return dict(kind='phase_cells', label=r['query']['label'], cells=[
            [g['input'], g['derived_preimage'], i] for i, g in enumerate(results)
            if g['status'] == 'certified'])
    q = r['query']['requests'][0]
    _, selected = signed_spec(q)
    width = None if q['width']['kind'] == 'all_positive' else q['width']['bits']
    states, _ = target_domain(CAP, width)
    states = [list(s) for s in states if all(target_value(g, *s) for g in q['guards'])]
    basis = next((i for i, g in enumerate(results) if g['status'] == 'certified'), None)
    formula = None if basis is None else signed_spec(r['query']['requests'][basis])[0]['target']
    return dict(kind='guarded_boolean', selection=selected, width=q['width'], guards=q['guards'],
                count_cap=CAP, states=states, basis_goal=basis,
                values=None if basis is None else [target_value(formula, *s) for s in states])
