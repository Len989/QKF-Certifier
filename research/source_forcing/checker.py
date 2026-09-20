"""Portable consumer proof checker. No producer, search, or source_cell calls."""
from research.pure_rows.common import InvalidCertificate
from .context import (SEEDS, conclude, encoded, fields, integer, need,
                      prepare, snapshot)
from .bridge import verify_descent, verify_preparation, verify_presentation


def checked_lookups(ctx, lookups, derive):
    targets = list(dict.fromkeys(g[0] for g in ctx['request']['goals']))
    need(type(lookups) is list and len(lookups) == len(targets), 'complete distinct goal proofs')
    values = {}
    for target, item in zip(targets, lookups):
        fields(item, ('input', 'output'))
        need(type(item['input']) is int and item['input'] == target, 'goal proof order')
        integer(item['output'], 0, 7)
        expected = derive(target)
        need(item['output'] == expected, 'false direct goal derivation')
        values[target] = expected
    return values


def _check(ctx, cert):
    fields(cert, ('schema', 'binding', 'kind', 'preparation', 'evidence'))
    need(cert['schema'] == 'qkf-source-forcing-proof-v1' and
         encoded(cert['binding']) == encoded(ctx['binding']), 'source/request/ruleset proof binding')
    route = cert['kind']
    need(route in ('forcing', 'no_saturation', 'direct_seeds', 'direct_cell'), 'proof route')
    transitions, seeds = verify_preparation(ctx, cert['preparation'], route != 'direct_cell')
    evidence = cert['evidence']
    if route == 'forcing':
        fields(evidence, ('presentation', 'pure_rows', 'descent'))
        p = verify_presentation(ctx, evidence['presentation'], seeds)
        from research.pure_rows.checker import check as check_rows
        result = check_rows(p, evidence['pure_rows'])
        verify_descent(evidence['descent'], result)
        row = result['rows'][0]
        need(row['generated_domain'] == list(SEEDS), 'generated source seed subalgebra')
        values = {a: value for a, value in enumerate(row['forced_values']) if value is not None}
        return conclude(ctx, values, route=route, generated=row['generated_domain'], forced=row['forced_domain'])
    if route == 'no_saturation':
        fields(evidence, ('presentation', 'domain', 'values'))
        verify_presentation(ctx, evidence['presentation'], seeds)
        need(encoded(evidence['domain']) == encoded(list(SEEDS)) and
             encoded(evidence['values']) == encoded([[a, seeds[a]] for a in SEEDS]), 'generated-only evidence')
        # The four registered inputs are already a subalgebra. This check does
        # no congruence/kernel saturation and cannot answer an external goal.
        for a in SEEDS:
            for b in SEEDS:
                need(a | b in seeds and a & b in seeds, 'seed domain is not closed')
                need(seeds[a | b] == seeds[a] | seeds[b] and seeds[a & b] == seeds[a] & seeds[b],
                     'generated action compatibility')
        return conclude(ctx, seeds, route=route, generated=list(SEEDS))
    if route == 'direct_seeds':
        fields(evidence, ('rule', 'atomic_images', 'lookups'))
        need(evidence['rule'] == 'disjoint-phase-range-v1', 'direct range rule')
        # For a function into exactly {A,B,C}, h(ABC) is the output guard K.
        # Its three disjoint fibres are K\h(BC), h(B), h(BC)\h(B).
        # This uses the checked concrete inverse-image meaning, not an
        # unproved complement law in the pure-row signature.
        k, b, bc = seeds[7], seeds[2], seeds[6]
        need(b & bc == b and bc & k == bc and seeds[0] == 0, 'nested checked seed fibres')
        images = [k & (7 ^ bc), b, bc & (7 ^ b)]
        need(encoded(evidence['atomic_images']) == encoded(images), 'direct disjoint phase decomposition')

        def derive(target):
            value = 0
            for i, atom in enumerate(images):
                if target & (1 << i):
                    value |= atom
            return value
    else:
        fields(evidence, ('rule', 'lookups'))
        need(evidence['rule'] == 'direct-branch-membership-v1', 'direct cell rule')

        def derive(target):
            # Only requested distinct cells; no complete action table.
            value = 0
            for phase, (out, nxt) in enumerate(transitions):
                if out == ctx['request']['label'][3] and target & (1 << nxt):
                    value |= 1 << phase
            return value
    return conclude(ctx, checked_lookups(ctx, evidence['lookups'], derive), route=route)


def check(source, request, raw_certificate):
    try:
        cert = snapshot(raw_certificate)
        ctx = prepare(source, request)
        return _check(ctx, cert)
    except (ValueError, TypeError, KeyError, IndexError, RecursionError) as exc:
        raise InvalidCertificate(str(exc)) from exc
