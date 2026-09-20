"""Strict local contract and retained Graal source admission, without discovery."""
import hashlib
from pathlib import Path
import sys

from research.pure_rows.common import (digest, encoded, fields, integer, need,
                                       read_json, snapshot, write_json)

PROFILE = 'graal-ascending-physical-phases-v1'
RULESET = 'physical-inverse-image-union-intersection-v1'
PHASES = ((False, 0), (True, 0), (True, 1))
SEEDS = (0, 2, 6, 7)
SOURCE_LIMIT = 2_000_000


class Unsupported(ValueError):
    pass


def legacy():
    """Contain the retained scripts' path setup; do not rewrite archival code."""
    saved = sys.path[:]
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'graal'))
        from research.graal import lower_source
        import carry_kernel
        return lower_source, carry_kernel
    finally:
        sys.path[:] = saved


def prepare(source, raw_request):
    try:
        need(type(source) is str and len(source.encode()) <= SOURCE_LIMIT, 'source size/type')
        req = snapshot(raw_request)
        fields(req, ('schema', 'profile', 'label', 'goals'))
        need(req['schema'] == 'qkf-local-forcing-request-v1' and req['profile'] == PROFILE,
             'local request/profile')
        label = req['label']
        need(type(label) is list and len(label) == 4, 'label m,a,g,y')
        m, a, g, y = [integer(x, 0, 1) for x in label]
        need(m <= g <= a, 'admissible source mask/input cell')
        need(type(req['goals']) is list and 1 <= len(req['goals']) <= 16, 'goal count')
        for goal in req['goals']:
            need(type(goal) is list and len(goal) == 2, 'goal input and claimed preimage')
            for x in goal:
                integer(x, 0, 7)
        compiler, _ = legacy()
        ir = compiler.compile_source(source)
        binding = dict(source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                       request_sha256=digest(req), ir_sha256=digest(ir),
                       profile=PROFILE, ruleset=RULESET)
        return dict(request=req, program=ir['carry_program'], binding=binding)
    except (ValueError, TypeError, KeyError, IndexError, RecursionError) as exc:
        raise Unsupported(str(exc)) from exc


def operator_name(ctx):
    return 'guarded-preimage:' + ','.join(map(str, ctx['request']['label']))


def conclude(ctx, values, *, route, generated=None, forced=None):
    goals = []
    cache = {}
    for target, claim in ctx['request']['goals']:
        if target not in cache:
            cache[target] = values.get(target)
        actual = cache[target]
        status = 'unresolved' if actual is None else 'certified' if actual == claim else 'refuted'
        item = dict(input=target, claimed_preimage=claim, derived_preimage=actual, status=status)
        if status == 'refuted':
            # A physical phase in the symmetric difference witnesses a false set equality.
            item['separating_phase'] = next(i for i in range(3) if (actual ^ claim) & (1 << i))
        goals.append(item)
    statuses = {g['status'] for g in goals}
    status = 'refuted' if 'refuted' in statuses else 'unresolved' if 'unresolved' in statuses else 'certified'
    return dict(schema='qkf-local-forcing-result-v1', status=status, binding=ctx['binding'],
                route=route, goals=goals, generated_domain=generated, forced_domain=forced,
                scope='one guarded nonsign ascending-loop cell on three physical phases; no whole-word or signed-profile theorem',
                lean_checked=False)
