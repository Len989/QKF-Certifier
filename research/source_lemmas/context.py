"""One admitted source and one exact scope, independent of the first goal."""
from dataclasses import replace
from research.wordexpr.frontend import Unsupported
from research.signed_context.io import freeze, thaw, source_text
from research.source_query.context import (Context, prepare as old_prepare, target_domain,
    snapshot, digest, canonical, load_json, save_json, integer, RULESET)
from research.source_query.encoding import signature
from research.ground_query.schema import fields, require
from research.unified.v3_schema import compile_target, SIGNED_KIND
from research.signed_predicates.frontend import goal
from research.signed_bridge.model import request as selection
from research.source_planner.context import options as previous_options

SCHEMA = 'qkf-source-lemma-batch-v1'
PAYLOAD = 'qkf-source-lemma-packet-v1'
LIMIT = 4
DEFAULTS = dict(max_work=20_000_000, max_fact_attempts=2048, max_rounds=512,
                max_horizon=128, max_witness_width=8, max_witness_evaluations=510,
                max_source_states=64, max_product_states=8192, max_lemmas=64)


def options(raw=None):
    raw = {} if raw is None else snapshot(raw)
    require(type(raw) is dict and set(raw) <= set(DEFAULTS), 'lemma limits')
    out = {**DEFAULTS, **raw}
    maximum = out.pop('max_lemmas')
    integer(maximum, 0, 64, 'lemma storage limit')
    return dict(previous_options(out), max_lemmas=maximum)


def requests(raw):
    value = snapshot(raw)
    fields(value, ('schema', 'requests'), 'independent goal batch')
    require(value['schema'] == SCHEMA and type(value['requests']) is list
            and 0 < len(value['requests']) <= 64, '1..64 independent requests')
    return value['requests']


def target_context(ctx, raw):
    r = snapshot(raw)
    fields(r, ('schema', 'target', 'guards', 'width'), 'source query')
    require(r['schema'] == 'qkf-guarded-source-query-v1', 'source query schema')
    require(freeze(r['guards']) == freeze(ctx.guards) and freeze(r['width']) == freeze(ctx.request['width']),
            'guard/width differs from checked context; load a new scope')
    compiled = compile_target(r['target'])
    require(compiled['kind'] == SIGNED_KIND and r['target']['schema'] == 'qkf-target-v2',
            'signed qkf-target-v2 required')
    spec = compiled['specification']
    require(selection(spec['entry'], spec['word_type']) == ctx.selection,
            'consumer selects a different source/profile')
    if goal(spec) > LIMIT:
        raise Unsupported('lemma native algebra supports target counts 0..3')
    return replace(ctx, request=r, spec=spec)


def prepare(source, raw):
    source = source_text(source)
    items = requests(raw)
    ctx = old_prepare(source, items[0])
    if ctx.limit > LIMIT:
        raise Unsupported('lemma native algebra supports guard/target counts 0..3')
    ctx.limit = LIMIT
    states, ctx.domain_edges = target_domain(LIMIT, ctx.width)
    ctx.domain = tuple(s for s in states if ctx.guard(*s))
    for item in items:
        target_context(ctx, item)
    return ctx, items


def scope(ctx):
    return dict(source=dict(source_sha256=ctx.ir['source_sha256'], ir_sha256=digest(ctx.ir),
                            selection=ctx.selection),
                profile=ctx.binding()['contract'], native_ruleset=RULESET,
                native_algebra=signature(ctx), guards=ctx.guards, width=ctx.request['width'],
                domain='nonempty modular words satisfying the exact guard conjunction',
                guarantee='conditional_closed_ground_equality', target_count_cap=LIMIT)


def context_json(ctx):
    return freeze(dict(request=ctx.request, selection=ctx.selection, ir=ctx.ir, spec=ctx.spec,
                       guards=ctx.guards, width=ctx.width, limit=ctx.limit,
                       domain=[list(s) for s in ctx.domain], domain_edges=ctx.domain_edges))


def from_context_json(raw):
    value = thaw(raw)
    value['domain'] = tuple(tuple(s) for s in value['domain'])
    return Context(**value)
