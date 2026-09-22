"""PR49 registrations; delivery and cold verification contracts remain PR47."""
from pathlib import Path
from research.sdk_comparison.common import (
    canonical, digest, load_json, save_json, require, checkpoint_json, schedule,
    identity, compare_identity, inventory, check_inventory, metrics, validate_attempts,
    validate_case, one_request, delivery, aggregate, ENVELOPE)
from research.sdk_comparison.common import members as old_members

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SHARDS = ('single', 'mask', 'parity', 'repeat', 'each', 'fallback')


def registered(shard='all'):
    protocol, reg = load_json(HERE / 'PROTOCOL.json'), load_json(HERE / 'REGISTRATION.json')
    require(digest(protocol) == reg['protocol_sha256'], 'registered protocol changed')
    require(shard == 'all' or shard in SHARDS, 'unknown shard')
    if shard != 'all':
        reg = dict(reg, cases=[c for c in reg['cases'] if c['shard'] == shard])
    return protocol, reg


def members(case, route):
    require(route in case['routes'], 'unregistered route')
    if route.startswith(('each_prepared_', 'each_emitted_')):
        return [(one_request(case['request'], i), route[len('each_'):])
                for i in range(len(case['request']['query']['requests']))]
    return old_members(case, route)
