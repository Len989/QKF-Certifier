"""Replay complete artifact set and causal accounting in a fresh search-free process."""
import json
from pathlib import Path
import sys
from .common import (load_json, require, registered, validate_case, check_inventory,
                     compare_identity, digest, matched_verdicts, validate_attempts)


def run(root):
    from research.applicable_summary.replay import NoSearch
    guard = NoSearch()
    require(not guard.loaded(), 'fresh replay required')
    sys.meta_path.insert(0, guard)
    try:
        from .verify import verify_record
        from .analysis import analyze, causal_checks
        check_inventory(root)
        protocol, reg = registered()
        require(load_json(root / 'PROTOCOL.json') == protocol and load_json(root / 'REGISTRATION.json') == reg,
                'exact registered protocol and population')
        packets = checkpoints = applications = 0
        attempts = load_json(root / 'ATTEMPTS.json')
        validate_attempts(attempts, reg, protocol['measurement']['timing_repeats'])
        errors = []
        for entry in reg['cases']:
            case = load_json(root / entry['name'] / 'case.json')
            validate_case(case, entry)
            arms = {}
            for route in case['routes']:
                if route in case['unavailable']:
                    continue
                folder = root / case['name'] / route
                if not (folder / 'audit.json').exists():
                    errors.append(case['name'] + '/' + route + ': missing audit')
                    continue
                saved = load_json(folder / 'audit.json')
                arms[route] = saved
                try:
                    checked = verify_record(case, route, saved, history=True, repetitions=1)
                    packets += checked['packets']
                    checkpoints += checked['checkpoints']
                    applications += checked['warm_apply_calls']
                    compare_identity(saved, load_json(folder / 'memory.json'))
                    for n in range(protocol['measurement']['timing_repeats']):
                        compare_identity(saved, load_json(folder / f'timing-{n}.json'))
                except Exception as error:
                    errors.append(case['name'] + '/' + route + ': ' + str(error))
            matched_verdicts([a['result']['status'] for a in arms.values()])
            causal_checks(case, arms)
        require(not errors, 'replay failures: ' + repr(errors))
        require(not load_json(root / 'FAILURES.json') and all(a['status'] == 'passed' for a in attempts), 'recorded failed attempt')
        fresh, derived = analyze(root, write=False, details=True)
        require(fresh == load_json(root / 'SUMMARY.json'), 'summary/decision differs from full measurements')
        for name, expected in derived.items():
            require(load_json(root / name) == expected, 'derived report differs: ' + name)
        require(packets == fresh['semantic']['packets'], 'packet denominator')
        require(not guard.loaded(), 'search module imported')
        return dict(status='passed', packets=packets, checkpoints=checkpoints, applications=applications,
                    search_imports=0, complete_attempts=len(attempts),
                    timings_certified=False, telemetry_is_execution_proof=False,
                    source_execution_for_positive_or_apply=False)
    finally:
        sys.meta_path.remove(guard)


if __name__ == '__main__':
    print(json.dumps(run(Path(sys.argv[1])), sort_keys=True))
