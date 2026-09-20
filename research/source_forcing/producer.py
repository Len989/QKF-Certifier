"""Source facts, pure-row forcing, and fully charged direct controls."""
from .audit import Audit
from .context import (SEEDS, Unsupported, digest, encoded, fields, integer, need, prepare)
from . import native


def prove(source, request, *, route='forcing', limits=None):
    need(route in ('forcing', 'no_saturation', 'direct_seeds', 'direct_cell'), 'route')
    limits = dict(max_work=5_000_000) if limits is None else limits
    fields(limits, ('max_work',))
    integer(limits['max_work'], 0, 20_000_000)
    audit = Audit(route)
    cert, row_work, preparation_hash = None, None, None
    caches = dict(goal_requests=0, distinct_goals=0, goal_cache_hits=0)
    lookup_trace = []
    with audit:
        try:
            with audit.stage('source_admission'):
                ctx = prepare(source, request)
            with audit.stage('physical_branch_facts'):
                try:
                    branches = native.branches(ctx)
                except ValueError as exc:
                    raise Unsupported('local source-cell semantics: ' + str(exc)) from exc
            with audit.stage('source_seeds_and_compatibility'):
                facts = [] if route == 'direct_cell' else [native.native_seed(ctx, branches, a) for a in SEEDS]
                prep = dict(branches=branches, seeds=facts,
                            compatibility=None if route == 'direct_cell' else native.compatibility())
                preparation_hash = digest(prep)
                seeds = {f['input']: f['output'] for f in facts}
            evidence = None
            if route in ('forcing', 'no_saturation'):
                with audit.stage('native_tables'):
                    p = native.presentation(ctx, facts)
                if route == 'forcing':
                    with audit.stage('pure_row_saturation_and_builtin_checks'):
                        from research.pure_rows.producer import produce
                        rows, proof, row_work = produce(p, limits)
                        # Certificates use the retained strict integer-only JSON
                        # reader; keep diagnostic durations in integer ns too.
                        row_work = {k[:-8] + '_ns' if k.endswith('_seconds') else k:
                                    round(v * 1_000_000_000) if k.endswith('_seconds') else v
                                    for k, v in row_work.items()}
                    if proof is None:
                        result = dict(status='budget_exhausted', binding=ctx['binding'], route=route,
                                      stage=rows['stage'], resource=rows['resource'])
                    else:
                        evidence = dict(presentation=p, pure_rows=proof,
                                        descent=dict(rule='identity-on-physical-powerset',
                                                     carrier_partition=[[i] for i in range(8)]))
                else:
                    evidence = dict(presentation=p, domain=list(SEEDS), values=[[a, seeds[a]] for a in SEEDS])
            else:
                from .direct import action_cell, atoms, range_value
                with audit.stage('direct_goal_derivations'):
                    cache = {}
                    images = atoms(seeds) if route == 'direct_seeds' else None
                    for target, _ in ctx['request']['goals']:
                        caches['goal_requests'] += 1
                        hit = target in cache
                        lookup_trace.append(dict(input=target, cache_hit=hit))
                        if hit:
                            caches['goal_cache_hits'] += 1
                            continue
                        caches['distinct_goals'] += 1
                        cache[target] = range_value(images, target) if route == 'direct_seeds' else action_cell(ctx, branches, target)
                    lookups = [dict(input=a, output=b) for a, b in cache.items()]
                    evidence = dict(rule='disjoint-phase-range-v1' if route == 'direct_seeds' else 'direct-branch-membership-v1',
                                    lookups=lookups)
                    if route == 'direct_seeds':
                        evidence['atomic_images'] = images
            if evidence is not None:
                cert = dict(schema='qkf-source-forcing-proof-v1', binding=ctx['binding'], kind=route,
                            preparation=prep, evidence=evidence)
                with audit.stage('independent_consumer_check'):
                    from .checker import check
                    result = check(source, request, cert)
                if route in ('forcing', 'no_saturation'):
                    # These routes precompute one checked row/domain. Requests
                    # are paid lookups with the same ordinary duplicate cache.
                    seen = set()
                    with audit.stage('goal_lookups'):
                        for target, _ in ctx['request']['goals']:
                            hit = target in seen
                            lookup_trace.append(dict(input=target, cache_hit=hit))
                            caches['goal_requests'] += 1
                            caches['goal_cache_hits' if hit else 'distinct_goals'] += 1
                            seen.add(target)
        except Unsupported as exc:
            result = dict(status='unsupported', route=route, reason=str(exc))
        with audit.stage('certificate_encoding'):
            proof_bytes = len(encoded(cert)) if cert is not None else 0
    work = audit.report()
    work.update(caches=caches, goal_trace=lookup_trace, pure_rows=row_work,
                preparation_sha256=preparation_hash, certificate_bytes=proof_bytes,
                standalone_batch_bytes=proof_bytes,
                preparation_reused_within_batch=cert is not None,
                limits=limits)
    return cert, result, work
