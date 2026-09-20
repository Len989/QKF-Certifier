"""Registered sequential comparison; diagnostic costs, not a speedup claim."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

from .context import canonical, digest, load_json, save_json, require
from .fixtures import cases
from .producer import prove
from .checker import check


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    registration = load_json(Path(__file__).with_name('REGISTRATION.json'))
    save_json(root/'REGISTRATION.json', registration)
    save_json(root/'PROTOCOL.json', load_json(Path(__file__).with_name('PROTOCOL.json')))
    counts, checked, native_facts, completed = Counter(), 0, 0, 0
    diagnostics, comparisons = [], []
    try:
        population = list(cases())
        require(len(population) == len(registration['cases']), 'complete registered denominator')
        for case, registered in zip(population, registration['cases']):
            require(registered == {'name': case['name'], 'family': case['family'],
                    'expected': case['expected'], 'case_sha256': digest(case)}, 'registered case changed')
            folder = root / case['name']
            folder.mkdir()
            save_json(folder/'case.json', case)
            hashes, attempts, outcomes = [], [], []
            for route in ('query', 'ordinary'):
                proof, result, work = prove(case['source'], case['request'], route=route,
                                            limits=case['limits'], fallback=case['fallback'])
                save_json(folder/(route+'.json'), {'certificate': proof, 'result': result, 'work': work})
                require(result['status'] == case['expected'], 'unexpected outcome: '+case['name']+'/'+route)
                if proof is not None:
                    require(check(case['source'], case['request'], proof) == result, 'independent replay differs')
                    checked += 1
                    native_facts += result.get('checked_native_facts', 0)
                    if proof['kind'] == 'ground':
                        require(work['counts'].get('legacy_builder_calls', 0) == 0, 'hidden source construction')
                hashes.append(work['ground_request_sha256'])
                attempts.append(work['fact_attempts'])
                outcomes.append(result['status'])
                counts[result['status']] += 1
                diagnostics.append({'name': case['name'], 'family': case['family'], 'route': route,
                                    'status': result['status'], 'counts': work['counts'],
                                    'closure': work['closure'], 'elapsed_ns_instrumented': work['elapsed_ns'],
                                    'certificate_bytes': work['certificate_bytes']})
            require(hashes[0] == hashes[1] and attempts[0] == attempts[1], 'unfair native preparation')
            require(outcomes[0] == outcomes[1], 'completed consumer outcomes disagree')
            comparisons.append({'name': case['name'], 'same_native_attempts': True,
                                'same_ground_request': True, 'same_outcome': True})
            completed += 1
        summary = {'schema': 'qkf-source-query-experiment-v1', 'status': 'passed',
                   'semantic': {'cases': len(population), 'routes': 2, 'certificates': checked,
                                'checked_native_facts': native_facts, 'statuses': dict(counts)},
                   'comparisons': comparisons,
                   'scope': 'development conformance; diagnostic cost of identical native preparation and two closure algorithms; no source speedup, forcing or Lean claim'}
        save_json(root/'SUMMARY.json', summary)
        save_json(root/'COSTS.json', {'python': sys.version, 'instrumented': True, 'runs': diagnostics})
        save_json(root/'FAILURES.json', [])
        inventory = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(root.rglob('*')) if p.is_file()}
        save_json(root/'MANIFEST.json', inventory)
        return summary
    except BaseException as error:
        failure = root/'FAILURES.json'
        if not failure.exists():
            save_json(failure, [{'completed_cases': completed, 'error': type(error).__name__+': '+str(error)}])
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    print(json.dumps(run(parser.parse_args().output), sort_keys=True))
