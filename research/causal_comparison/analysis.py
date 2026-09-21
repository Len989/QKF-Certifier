"""Deterministic contrasts; no ranking across different semantic profiles."""
from collections import Counter
from .common import (canonical, load_json, save_json, require, backend, metrics,
                     registered, validate_case, compare_identity, matched_verdicts)


def causal_checks(case, arms):
    checks = []
    if 'direct41' in arms and 'query41' in arms:
        a, b = backend(arms['direct41']), backend(arms['query41'])
        require(a['fact_attempts'] == b['fact_attempts'], 'II comparison changed native preparation')
        require(a['ground_request_sha256'] == b['ground_request_sha256'], 'II comparison changed E/query')
        checks.append(dict(kind='II_backend', same_native_attempts=True, same_ground_request=True,
                           direct_counts=a['counts'], query_counts=b['counts']))
    sdk = [r for r in ('sdk_default', 'sdk_reuse', 'sdk_direct') if r in arms]
    if len(sdk) == 3:
        attempts = [backend(arms[r])['fact_attempts'] for r in sdk]
        require(attempts[0] == attempts[1] == attempts[2], 'SDK controls changed native attempts')
        without = backend(arms['sdk_default'])
        require(not (without.get('foundations') or {}).get('E_plus'), 'no-lemmas arm contains a derived lemma')
        checks.append(dict(kind='reuse_backend', same_native_attempts=True, ordinary_cache_in_all=True,
                           derived_lemma_counts={r: len((backend(arms[r]).get('foundations') or {}).get('E_plus', [])) for r in sdk},
                           actual_later_lemma_goals={r: backend(arms[r])['counts'].get('later_goals_using_lemma', 0) for r in sdk}))
        if case['group'] == 'cold_series' and case['family'] in ('mask', 'parity'):
            n = len(case['request']['query']['requests'])
            for r in ('sdk_reuse', 'sdk_direct'):
                w = backend(arms[r])
                require(w['counts'].get('lemma_promotions') == 1 and
                        w['counts'].get('later_goals_using_lemma', 0) == n - 1, 'actual shared lemma required')
                successful = [p for p in w['checkpoints'] if p['result']['status'] == 'certified'
                              and p['item'].get('via_lemma') is not None]
                require(len(successful) >= n - 1, 'lemma availability is not actual proof use')
        if case['family'] == 'ordinary_cache':
            for r in sdk:
                require(backend(arms[r])['counts'].get('exact_goal_cache_hits') == 15, 'ordinary exact cache fairness')
    if 'planner43' in arms and 'eager43' in arms:
        adaptive, eager = backend(arms['planner43']), backend(arms['eager43'])
        chosen = {canonical(x['candidate']) for x in adaptive['fact_attempts']}
        not_requested = [x for x in eager['fact_attempts'] if canonical(x['candidate']) not in chosen]
        checks.append(dict(kind='observation_selection', adaptive_requests=len(adaptive['fact_attempts']),
                           eager_requests=len(eager['fact_attempts']),
                           eager_candidates_not_requested=not_requested,
                           same_permitted_rules=True, desired_target_is_not_a_premise=True))
    for route, arm in arms.items():
        if route != 'retained':
            require(not arm['trace']['counts'].get('legacy_coverage_builds', 0), 'hidden legacy coverage')
            require(not arm['trace']['counts'].get('global_source_quotient_calls', 0), 'hidden global source quotient')
    if case['group'] == 'phase' and all(r in arms for r in ('phase_forcing', 'phase_direct_seeds', 'phase_direct_cell')):
        forcing = arms['phase_forcing']
        if forcing['certificate'] is not None:
            from research.signed_compact.dag import unpack
            from research.source_forcing.checker import check
            f, d, c = [unpack(arms[r]['certificate'])['evidence'] for r in
                       ('phase_forcing', 'phase_direct_seeds', 'phase_direct_cell')]
            require(f['preparation'] == d['preparation'], 'forcing/direct-seed preparation differs')
            require(f['preparation']['branches'] == c['preparation']['branches'], 'physical source work differs')
            verified = check(case['source'], case['request']['query'], f)
            generated, forced = verified['generated_domain'], verified['forced_domain']
            requested_outside = sorted({x for x, _ in case['request']['query']['goals'] if x in forced and x not in generated})
            require(not backend(forcing)['counts'].get('direct_action_queries', 0), 'forcing directly queried target')
            require(not any(t['call'] == 'target' for t in backend(forcing)['trace']), 'target call in forcing trace')
            checks.append(dict(kind='I_source_bound', generated=generated, forced=forced,
                requested_in_D_minus_S=requested_outside, same_seeds_as_direct=True,
                same_physical_branches=True, no_direct_target_call=True,
                structural_counts={r: backend(arms[r])['counts'] for r in arms}))
    return checks


def analyze(root, *, write=True, details=False):
    protocol, reg = registered()
    repetitions = protocol['measurement']['timing_repeats']
    rows, causal, coverage, failures = [], [], [], load_json(root / 'FAILURES.json')
    unavailable = packets = 0
    for entry in reg['cases']:
        case = load_json(root / entry['name'] / 'case.json')
        validate_case(case, entry)
        arms = {}
        for route in case['routes']:
            folder = root / case['name'] / route
            if route in case['unavailable']:
                require(load_json(folder / 'UNAVAILABLE.json')['reason'] == case['unavailable'][route], 'unavailable contract')
                unavailable += 1
                coverage.append(dict(case=case['name'], route=route, status='contract_not_supported'))
                continue
            if not (folder / 'audit.json').exists():
                coverage.append(dict(case=case['name'], route=route, status='failed_attempt'))
                continue
            saved = load_json(folder / 'audit.json')
            arms[route] = saved
            status = saved['result']['status']
            coverage.append(dict(case=case['name'], route=route, status=status))
            packets += int(saved['certificate'] is not None)
            if not (folder / 'memory.json').exists():
                continue
            memory = load_json(folder / 'memory.json')
            compare_identity(saved, memory)
            trials, checks = [], []
            for n in range(repetitions):
                if not (folder / f'timing-{n}.json').exists() or not (folder / f'timing-{n}-check.json').exists():
                    continue
                trial, checked = load_json(folder / f'timing-{n}.json'), load_json(folder / f'timing-{n}-check.json')
                compare_identity(saved, trial)
                require(checked['semantics']['result_sha256'] == saved['identity']['result_sha256'], 'cold check trial identity')
                trials.append(trial)
                checks.append(checked)
            if len(trials) != repetitions:
                continue
            if case['request']['profile'].startswith('graal'):
                width, goals = 'local_phases', len(case['request']['query']['goals'])
            else:
                q = case['request']['query']['requests'][0]
                width = 'all' if q['width']['kind'] == 'all_positive' else 'fixed' + str(q['width']['bits'])
                goals = len(case['request']['query']['requests'])
            work = backend(saved)
            builds = [t['build_ns'] for t in trials]
            colds = [c['cold_check_ns'] for c in checks]
            apply = [c['warm_apply_ns'] for c in checks]
            full = [b + c for b, c in zip(builds, colds)]
            row = dict(case=case['name'], family=case['family'], group=case['group'], route=route,
                width=width, goals=goals, status=status,
                common_research_calls=saved['trace']['counts']['research_calls'],
                structural_counts=saved['trace']['counts'], backend_counts=work.get('counts', {}),
                fact_requests=len(work.get('fact_attempts', [])), native_attempts=work.get('fact_attempts', []),
                certificate_bytes=saved['certificate_bytes'], diagnostic_bytes=saved['diagnostic_bytes'],
                source_bytes=saved['source_bytes'], request_bytes=saved['request_bytes'],
                traced_peak_bytes=memory['traced_peak_bytes'], build_ns=metrics(builds),
                cold_check_ns=metrics(colds), proof_scenario_ns=metrics(full),
                warm_apply_ns=metrics(apply) if all(x is not None for x in apply) else None,
                application_calls=checks[0]['warm_apply_calls'],
                application_scenario_ns=metrics([f + a for f, a in zip(full, apply)]) if all(x is not None for x in apply) else None,
                audit_phase_ns=saved['trace']['audit_phase_ns'])
            # Process-level costs include startup, imports, I/O and diagnostics.
            row['process_scenario_ns'] = metrics([
                load_json(folder / f'timing-{n}.process.json')['process_elapsed_ns'] +
                load_json(folder / f'timing-{n}-check.process.json')['process_elapsed_ns'] for n in range(repetitions)])
            rows.append(row)
        matched_verdicts([a['result']['status'] for a in arms.values()])
        causal.append(dict(case=case['name'], family=case['family'], checks=causal_checks(case, arms)))
    scheduled = sum(len(e['routes']) for e in reg['cases'])
    by_route = {}
    for row in coverage:
        by_route.setdefault(row['route'], Counter())[row['status']] += 1
    selection_families = sorted({c['family'] for c in causal if any(
        x['kind'] == 'observation_selection' and x['adaptive_requests'] < x['eager_requests'] for x in c['checks'])})
    phase_d_s = [c['case'] for c in causal if any(x['kind'] == 'I_source_bound' and x['requested_in_D_minus_S'] for x in c['checks'])]
    break_even = []
    def lookup(name, route):
        return next((r for r in rows if r['case'] == name and r['route'] == route), None)
    for family in ('mask', 'parity'):
        for width in ('all', 'fixed8'):
            for route in ('sdk_reuse', 'sdk_direct'):
                record = dict(family=family, width=width, route=route, reference='sdk_default', metrics={})
                for metric in ('common_research_calls', 'certificate_bytes', 'proof_scenario_ns', 'application_scenario_ns'):
                    non_losing = []
                    for n in (1, 4, 16):
                        a, b = lookup(f'batch_{family}_{width}_{n}', route), lookup(f'batch_{family}_{width}_{n}', 'sdk_default')
                        if a is None or b is None:
                            continue
                        av, bv = a[metric], b[metric]
                        av = av['median'] if type(av) is dict else av
                        bv = bv['median'] if type(bv) is dict else bv
                        if av is not None and bv is not None and av <= bv:
                            non_losing.append(n)
                    record['metrics'][metric] = dict(first_measured_prefix=min(non_losing) if non_losing else None,
                                                     non_losing_measured_prefixes=non_losing)
                break_even.append(record)
    direct_wins, retained_wins, II_wins = [], [], []
    for entry in reg['cases']:
        name = entry['name']
        a, b, c = lookup(name, 'sdk_default'), lookup(name, 'direct41'), lookup(name, 'retained')
        def win(x, y):
            return (x and y and x['status'] == y['status'] == 'certified' and
                    x['proof_scenario_ns']['median'] < y['proof_scenario_ns']['median'])
        if win(a, b):
            direct_wins.append(name)
        if win(a, c):
            retained_wins.append(name)
        if win(lookup(name, 'query41'), b):
            II_wins.append(name)
    decision = dict(
        engineering='passed' if not failures and len(rows) == scheduled - unavailable else 'failed',
        structural_selection_families=selection_families,
        two_family_structural_selection=len(selection_families) >= 2,
        I_requested_D_minus_S=phase_d_s,
        SDK_median_proof_cost_wins_vs_simple_direct=direct_wins,
        SDK_median_proof_cost_wins_vs_stronger_retained=retained_wins,
        II_median_proof_cost_wins_vs_same_native_ordinary=II_wins,
        defaults=dict(signed='no_lemmas', phase='direct_cell', derived_lemmas='explicit opt-in'),
        F1='not_implemented; block A formal acceptance remains open',
        next='bounded source-reasoning/IR pilot and F1; new external corpus only after engine freeze',
        interpretation='Development medians with intrinsic instrumentation. Local structural savings and checked mechanisms are distinct from total-cost or competitive/product acceptance.')
    report = dict(schema='qkf-causal-comparison-result-v1', status=decision['engineering'],
                  semantic=dict(cases=len(reg['cases']), scheduled_arms=scheduled, unavailable_arms=unavailable,
                                executed_arms=scheduled - unavailable, packets=packets,
                                timing_builds=(scheduled - unavailable) * repetitions,
                                statuses={r: dict(c) for r, c in by_route.items()}),
                  decision=decision, failures=len(failures), break_even=break_even)
    data = {'COSTS.json': rows, 'CAUSAL.json': causal, 'DECISION.json': decision}
    if write:
        for name, value in data.items():
            save_json(root / name, value)
    return (report, data) if details else report
