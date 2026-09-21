"""Registered cold series with fair ordinary caches and complete costs."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
from .context import canonical, digest, load_json, save_json, require, scope
from .fixtures import cases, ROUTES
from .producer import prove
from .checker import check, load_presentation


def decision(rows):
    table = []
    for family in ('mask', 'parity'):
        for width in ('all', 'fixed8'):
            record = dict(family=family, width=width, measured_prefixes=[1, 4, 16])
            for route in ('reuse', 'direct_cache'):
                record[route] = {}
                for metric in ('research_calls', 'elapsed_ns', 'ground_congruence_events'):
                    wins = []
                    for n in (1, 4, 16):
                        name = f'{family}_{width}_{n}'
                        a = next(r for r in rows if r['name'] == name and r['route'] == route)
                        b = next(r for r in rows if r['name'] == name and r['route'] == 'no_lemmas')
                        if a[metric] <= b[metric]:
                            wins.append(n)
                    record[route][metric] = dict(first_observed_break_even=min(wins) if wins else None,
                        non_losing_measured_prefixes=wins, reference='no_lemmas')
            table.append(record)
    any_work_win = any(row['reuse']['research_calls']['first_observed_break_even'] is not None
                       for row in table)
    recommendation = ('inspect the measured source/width prefixes before enabling derived lemmas'
                      if any_work_win else 'no same-backend research-call break-even within 16 on this registered corpus; '
                       'retain shared native/exact caches, limit derived lemmas to explicit experiments')
    return dict(gate='A2', rows=table, timings='single instrumented development run; no universal threshold',
        direct_control='same lemma eligibility and ordinary caches; any shared gain is not exclusive to I/II',
        contrasts=dict(reuse='same Paper II backend; derived lemma ablation',
                       direct_cache='combined ordinary backend and lemma versus Paper II without lemmas; '
                                    'not an isolated estimate of lemma return'),
        default_route='no_lemmas', lemma_routes='explicit experimental opt-in',
        recommendation=recommendation)


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    registration = load_json(Path(__file__).with_name('REGISTRATION.json'))
    protocol = load_json(Path(__file__).with_name('PROTOCOL.json'))
    save_json(root / 'REGISTRATION.json', registration)
    save_json(root / 'PROTOCOL.json', protocol)
    metrics, comparisons = [], []
    counts = {r: Counter() for r in ROUTES}
    batches = {r: Counter() for r in ROUTES}
    completed = packets = checkpoints = requested = 0
    try:
        require(digest(protocol) == registration['protocol_sha256'], 'registered protocol')
        population = list(cases())
        require(len(population) == len(registration['cases']), 'full registered population')
        for case, frozen in zip(population, registration['cases']):
            require(frozen == dict(name=case['name'], family=case['family'], case_sha256=digest(case),
                                   expected=case['expected']), 'registered source/goals/budgets/outcomes changed')
            folder = root / case['name']
            folder.mkdir()
            save_json(folder / 'case.json', case)
            attempts, statuses = {}, {}
            for route in ROUTES:
                proof, result, work = prove(case['source'], case['request'], route=route, limits=case['limits'])
                save_json(folder / (route + '.json'), dict(certificate=proof, result=result, work=work))
                actual = dict(status=result['status'], goals=[g['status'] for g in result['goals']])
                require(actual == case['expected'][route], 'unexpected outcome: ' + case['name'] + '/' + route)
                start = time.perf_counter_ns()
                if proof is not None:
                    require(check(case['source'], case['request'], proof) == result['goals'], 'independent cold package replay')
                    packets += 1
                elapsed = time.perf_counter_ns() - start
                if work['foundations'] is not None:
                    context, _ = load_presentation(case['source'], case['request'], work['foundations'])
                    for row in work['checkpoints']:
                        require(row['id'] == digest(dict(scope=scope(context.context()), request=row['request'], item=row['item'])),
                                'historical obligation identity')
                        require(context.verify(row['request'], row['item']).result() == row['result'], 'scoped historical proof')
                        checkpoints += 1
                counts[route].update(g['status'] for g in result['goals'])
                batches[route][result['status']] += 1
                requested += len(case['request']['requests'])
                attempts[route] = work['fact_attempts']
                statuses[route] = actual
                c = work['counts']
                metrics.append(dict(name=case['name'], family=case['family'], route=route,
                    status=result['status'], goals=len(result['goals']), counts=c, phases=work['phases'],
                    research_calls=c.get('research_calls', 0), elapsed_ns=work['elapsed_ns'],
                    ground_congruence_events=c.get('ground_congruence_events', 0),
                    external_package_replay_ns=elapsed, certificate_bytes=work['certificate_bytes'],
                    diagnostic_bytes=len(canonical(work).encode())))
                if case['family'] in ('mask', 'parity') and route != 'no_lemmas':
                    require(c.get('lemma_promotions') == 1, 'one nontrivial shared lemma required')
                    require(c.get('later_goals_using_lemma', 0) == len(result['goals']) - 1, 'all later independent goals use the lemma')
                if route == 'no_lemmas':
                    require(not (work['foundations'] or {}).get('E_plus'), 'ablation must not store a derived lemma')
                if case['name'] == 'exact_repeats_16':
                    require(c.get('exact_goal_cache_hits') == 15, 'every route gets the ordinary exact cache')
            require(attempts['reuse'] == attempts['direct_cache'] == attempts['no_lemmas'],
                    'controls must receive the same native attempts')
            comparisons.append(dict(name=case['name'], statuses=statuses, same_native_attempts=True))
            completed += 1
        semantic = dict(cases=len(population), routes=len(ROUTES), requested_goals=requested,
            packets=packets, checkpoints=checkpoints,
            batches={r: dict(v) for r, v in batches.items()}, goals={r: dict(v) for r, v in counts.items()})
        summary = dict(schema='qkf-source-lemmas-experiment-v1', status='passed', semantic=semantic,
                       comparisons=comparisons, paper_I_enabled=False, global_lemma_schemas=False)
        save_json(root / 'SUMMARY.json', summary)
        save_json(root / 'COSTS.json', dict(python=sys.version, runs=metrics, timing=protocol['timing']))
        save_json(root / 'A2.json', decision(metrics))
        save_json(root / 'FAILURES.json', [])
    except BaseException as error:
        save_json(root / 'FAILURES.json', [dict(type=type(error).__name__, message=str(error), completed_cases=completed,
                                               traceback=traceback.format_exc())])
        raise
    finally:
        save_json(root / 'MANIFEST.json', {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'MANIFEST.json'})
    return summary


if __name__ == '__main__':
    print(json.dumps(run(Path(sys.argv[1])), sort_keys=True))
