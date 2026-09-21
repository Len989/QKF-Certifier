"""Delivery contracts and deterministic artifact accounting; no search imports."""
from pathlib import Path
from copy import deepcopy
from research.causal_comparison.common import (canonical, digest, load_json, save_json,
    require, checkpoint_json, schedule, identity, compare_identity, inventory,
    check_inventory, metrics, validate_attempts)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SHARDS = ('core', 'mask', 'parity', 'repeat', 'phase', 'assessment')
ENVELOPE = 'qkf-sdk-comparison-delivery-v1'


def registered(shard='all'):
    protocol, reg = load_json(HERE / 'PROTOCOL.json'), load_json(HERE / 'REGISTRATION.json')
    require(digest(protocol) == reg['protocol_sha256'], 'registered protocol changed')
    require(shard == 'all' or shard in SHARDS, 'unknown shard')
    if shard != 'all':
        reg = dict(reg, cases=[c for c in reg['cases'] if c['shard'] == shard])
    return protocol, reg


def validate_case(case, entry):
    require(digest(case) == entry['case_sha256'] and case['name'] == entry['name'], 'registered task changed')
    require(case['routes'] == entry['routes'] and case['expected'] == entry['expected'], 'registered route/outcome')


def one_request(request, index):
    r = deepcopy(request)
    r['query']['requests'] = [r['query']['requests'][index]]
    return r


def delivery(case, route):
    if route == 'direct41':
        return 'native_proof_only'
    if case['group'] == 'phase':
        return 'local_phase'
    if route.startswith('each_'):
        return 'independent_certificates'
    if case['group'] in ('cold_series', 'assessment'):
        return 'consumer_service'
    return 'single_summary'


def members(case, route):
    """Exact independent requests and old verifier route for each produced proof."""
    require(route in case['routes'], 'route not registered')
    r = case['request']
    if route.startswith('each_'):
        return [(one_request(r, i), 'sdk_ordinary' if route.endswith('ordinary') else 'sdk_default')
                for i in range(len(r['query']['requests']))]
    if route.startswith('once_'):
        return [(one_request(r, 0), 'sdk_ordinary' if route.endswith('ordinary') else 'sdk_default')]
    return [(r, route)]


def queries(case):
    return [one_request(case['request'], i) for i in range(len(case['request']['query']['requests']))]


def aggregate(results):
    states = [r['status'] for r in results]
    for s in ('refuted', 'unsupported', 'budget_exhausted', 'unresolved'):
        if s in states:
            return s
    require(states and set(states) <= {'certified', 'verified_empty_domain'}, 'result statuses')
    return 'verified_empty_domain' if set(states) == {'verified_empty_domain'} else 'certified'
