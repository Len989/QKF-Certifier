"""Bounded planner options; semantic requests retain the PR41 contract."""
from research.source_query.context import (prepare, snapshot, digest, canonical,
                                         load_json, save_json, require, integer)

RULESET = 'bounded-ground-source-v1'
LANGUAGE = 'consumer-native-questions-v1'
DEFAULTS = dict(max_work=10_000_000, max_fact_attempts=512, max_rounds=256,
                max_horizon=128, max_witness_width=8, max_witness_evaluations=510,
                max_source_states=64, max_product_states=8192)


def options(raw):
    raw = {} if raw is None else snapshot(raw)
    require(type(raw) is dict and set(raw) <= set(DEFAULTS), 'planner limits')
    result = {**DEFAULTS, **raw}
    bounds = dict(max_work=20_000_000, max_fact_attempts=20000, max_rounds=4096,
                  max_horizon=128, max_witness_width=4096, max_witness_evaluations=100000,
                  max_source_states=64, max_product_states=8192)
    for name, high in bounds.items():
        integer(result[name], 1 if name in ('max_source_states', 'max_product_states') else 0, high, name)
    return result


def envelope(ctx, kind, evidence):
    return dict(schema='qkf-source-plan-proof-v1',
                binding=dict(source=ctx.binding(), checker_ruleset=RULESET),
                kind=kind, evidence=evidence)
