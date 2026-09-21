"""Registered sequential comparison, including every negative checkpoint."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import traceback

from .context import canonical, digest, load_json, save_json, require
from .fixtures import cases, ROUTES
from .producer import prove
from .checker import check


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    registration = load_json(Path(__file__).with_name('REGISTRATION.json'))
    protocol = load_json(Path(__file__).with_name('PROTOCOL.json'))
    save_json(root / 'REGISTRATION.json', registration)
    save_json(root / 'PROTOCOL.json', protocol)
    counts = {r: Counter() for r in ROUTES}
    completed, certificates, checkpoints = 0, 0, 0
    metrics, comparisons, question_sets = [], [], {}
    try:
        require(digest(protocol) == registration['protocol_sha256'], 'registered protocol')
        population = list(cases())
        require(len(population) == len(registration['cases']), 'full registered population')
        for case, frozen in zip(population, registration['cases']):
            require(frozen == dict(name=case['name'], family=case['family'], case_sha256=digest(case), expected=case['expected']), 'registered case changed')
            folder = root / case['name']
            folder.mkdir()
            save_json(folder / 'case.json', case)
            attempts, outcomes = {}, {}
            for route in ROUTES:
                proof, result, work = prove(case['source'], case['request'], route=route,
                                            limits=case['limits'], fallback=case['fallback'])
                save_json(folder / (route + '.json'), dict(certificate=proof, result=result, work=work))
                require(result['status'] == case['expected'][route], 'unexpected outcome: ' + case['name'] + '/' + route)
                if proof is not None:
                    require(check(case['source'], case['request'], proof) == result, 'independent consumer replay')
                    certificates += 1
                for previous in work['checkpoints']:
                    require(digest(previous['certificate']) == previous['id'], 'checkpoint identity')
                    require(check(case['source'], case['request'], previous['certificate']) == previous['result'], 'independent historical E replay')
                    checkpoints += 1
                attempts[route] = work['fact_attempts']
                outcomes[route] = result['status']
                counts[route][result['status']] += 1
                metrics.append(dict(name=case['name'], family=case['family'], route=route, status=result['status'],
                                    counts=work['counts'], elapsed_ns=work['elapsed_ns'],
                                    certificate_bytes=work['certificate_bytes'], checkpoints=len(work['checkpoints']),
                                    diagnostic_bytes=len(canonical(work).encode()), diagnosis=work['diagnosis']))
                if route == 'planner':
                    question_sets[case['name']] = [a['candidate'] for a in attempts[route]]
            require(attempts['planner'] == attempts['ordinary'], 'adaptive controls must receive the same native attempts')
            comparisons.append(dict(name=case['name'], same_adaptive_native_attempts=True, statuses=outcomes,
                                    native_attempts={r: len(attempts[r]) for r in ROUTES}))
            completed += 1
        require(question_sets['goal_true'] != question_sets['goal_negative'], 'consumer change must change questions')
        for name in ('mask_short_circuit', 'parity_short_circuit', 'irrelevant_local'):
            row = next(c for c in comparisons if c['name'] == name)
            require(row['native_attempts']['planner'] < row['native_attempts']['eager'], 'required early native-work reduction')
        summary = dict(schema='qkf-source-planner-experiment-v1', status='passed',
                       semantic=dict(cases=len(population), routes=3, certificates=certificates,
                                     checkpoints=checkpoints, statuses={r: dict(c) for r, c in counts.items()}),
                       comparisons=comparisons, goal_changed_questions=True,
                       scope='development comparison of bounded question selection and eager preparation; no global synthesis or I/II speedup claim')
        save_json(root / 'SUMMARY.json', summary)
        save_json(root / 'COSTS.json', dict(python=sys.version, runs=metrics,
                  timing='instrumented sequential single run per case/route; semantic state fresh, process caches retained; diagnostic only'))
        save_json(root / 'FAILURES.json', [])
        inventory = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(root.rglob('*')) if p.is_file()}
        save_json(root / 'MANIFEST.json', inventory)
        return summary
    except BaseException:
        if not (root / 'FAILURES.json').exists():
            save_json(root / 'FAILURES.json', [dict(completed_cases=completed, traceback=traceback.format_exc())])
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    print(json.dumps(run(parser.parse_args().output), sort_keys=True))
