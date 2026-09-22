"""Fresh search-free replay of the entire registered shard and cost derivation."""
import json
from pathlib import Path
import sys
from .common import (load_json, require, registered, validate_case, check_inventory,
                     compare_identity, canonical, validate_attempts)


def run(root):
    from .verify import NoSearch
    guard = NoSearch()
    require(not guard.loaded(), 'fresh replay required')
    sys.meta_path.insert(0, guard)
    try:
        from .verify import verify_record
        from .analysis import analyze
        check_inventory(root)
        shard = load_json(root / 'RUN.json')['shard']
        protocol, reg = registered(shard)
        require(load_json(root / 'PROTOCOL.json') == protocol and load_json(root / 'REGISTRATION.json') == reg,
                'exact protocol/population')
        attempts = load_json(root / 'ATTEMPTS.json')
        validate_attempts(attempts, reg, protocol['measurement']['timing_repeats'])
        packets = checkpoints = applications = 0
        errors = []
        for entry in reg['cases']:
            folder = root / entry['name']
            case = load_json(folder / 'case.json')
            validate_case(case, entry)
            for route in entry['routes']:
                try:
                    path = folder / route
                    saved = load_json(path / 'audit.json')
                    checked = verify_record(case, route, saved, history=True,
                                            repetitions=protocol['measurement']['warm_apply_repetitions'])
                    require(canonical(checked['semantic']) == canonical(load_json(path / 'audit-check.json')['semantic']),
                            'fresh receiver semantic identity')
                    packets += checked['packets']
                    checkpoints += checked['checkpoints']
                    applications += checked['warm_apply_calls']
                    compare_identity(saved, load_json(path / 'memory.json'))
                    for trial in range(protocol['measurement']['timing_repeats']):
                        compare_identity(saved, load_json(path / f'timing-{trial}.json'))
                except Exception as error:
                    errors.append(dict(case=case['name'], route=route, error=str(error)))
        require(not errors, 'replay failures: ' + repr(errors))
        fresh = analyze(root)
        require(canonical(fresh) == canonical(load_json(root / 'SUMMARY.json')), 'summary differs from raw samples')
        require((packets, checkpoints, applications) == tuple(fresh['semantic'][k] for k in ('packets','checkpoints','applications')),
                'semantic denominator')
        require(not guard.loaded(), 'search imported')
        return dict(status='passed', cases=len(reg['cases']), packets=packets, checkpoints=checkpoints,
                    applications=applications, attempts=len(attempts), search_imports=0,
                    source_execution_for_positive_or_apply=False, timings_certified=False)
    finally:
        sys.meta_path.remove(guard)


if __name__ == '__main__':
    print(json.dumps(run(Path(sys.argv[1])), sort_keys=True))
