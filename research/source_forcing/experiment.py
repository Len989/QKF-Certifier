"""Registered development comparison; failures and all cold preparation retained."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import traceback

from .audit import Audit
from .context import digest, need, read_json, write_json
from .fixtures import ROUTES, cases
from .producer import prove
from .checker import check


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    registration = read_json(Path(__file__).with_name('REGISTRATION.json'))
    protocol = read_json(Path(__file__).with_name('PROTOCOL.json'))
    write_json(root / 'REGISTRATION.json', registration)
    write_json(root / 'PROTOCOL.json', protocol)
    counts = {r: Counter() for r in ROUTES}
    diagnostics, comparisons, completed, certificates = [], [], 0, 0
    try:
        need(registration['protocol_sha256'] == digest(protocol), 'registered protocol')
        population = list(cases())
        need(len(population) == len(registration['cases']), 'complete registered denominator')
        for case, frozen in zip(population, registration['cases']):
            need(frozen == dict(name=case['name'], case_sha256=digest(case), expected=case['expected']), 'registered case changed')
            folder = root / case['name']
            folder.mkdir()
            write_json(folder / 'case.json', case)
            preps, results = {}, {}
            for route in ROUTES:
                cert, result, work = prove(case['source'], case['request'], route=route, limits=case['limits'])
                write_json(folder / (route + '.json'), dict(certificate=cert, result=result, work=work))
                need(result['status'] == case['expected'][route], 'unexpected outcome: ' + case['name'] + '/' + route)
                replay = None
                if cert is not None:
                    with Audit('replay') as audit:
                        got = check(case['source'], case['request'], cert)
                    replay = audit.report()
                    need(got == result, 'independent replay differs')
                    certificates += 1
                if route != 'direct_cell':
                    need(work['counts'].get('direct_action_queries', 0) == 0, 'hidden direct target query')
                preps[route] = work['preparation_sha256']
                results[route] = result
                counts[route][result['status']] += 1
                diagnostics.append(dict(name=case['name'], route=route, goals=len(case['request']['goals']),
                                        status=result['status'], work=work, independent_replay=replay))
            need(len({preps[r] for r in ROUTES[:3]}) == 1, 'forcing/control preparation differs')
            if case['name'].startswith('pilot_'):
                forced = results['forcing']
                need(forced['generated_domain'] == [0, 2, 6, 7] and forced['forced_domain'] == list(range(8)), 'pilot S<D')
                need(all(g['input'] not in forced['generated_domain'] for g in forced['goals']), 'pilot must need external cells')
                need(results['no_saturation']['status'] == 'unresolved', 'saturation ablation must leave an obligation')
                need(all(results[r]['status'] == 'certified' for r in ('forcing', 'direct_seeds', 'direct_cell')), 'pilot controls')
            comparisons.append(dict(name=case['name'], identical_four_seed_preparation=True,
                                    statuses={r: results[r]['status'] for r in ROUTES}))
            completed += 1
        summary = dict(schema='qkf-source-forcing-experiment-v1', status='passed',
                       semantic=dict(cases=len(population), routes=len(ROUTES), certificates=certificates,
                                     statuses={r: dict(c) for r, c in counts.items()}),
                       comparisons=comparisons,
                       mechanism=dict(source_bound=True, S=4, D=8, required_input=3,
                                      derived_preimage=0, direct_target_queries_on_forcing=0),
                       applicability=dict(gate='A1', mechanism='accepted_local_only',
                                          utility='not_established', default_route='direct',
                                          reason='same paid seeds admit a short Boolean range proof; saturation saves no physical phase evaluation here',
                                          pr43='query/planner/reuse may proceed without an I speedup'))
        write_json(root / 'SUMMARY.json', summary)
        write_json(root / 'COSTS.json', dict(python=sys.version, runs=diagnostics,
                   timing='instrumented diagnostic; sequential fresh semantic preparations, process/module caches retained; no wall-time speedup inference'))
        write_json(root / 'FAILURES.json', [])
        inventory = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(root.rglob('*')) if p.is_file()}
        write_json(root / 'MANIFEST.json', inventory)
        return summary
    except BaseException:
        if not (root / 'FAILURES.json').exists():
            write_json(root / 'FAILURES.json', [dict(completed_cases=completed, traceback=traceback.format_exc())])
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    print(json.dumps(run(parser.parse_args().output), sort_keys=True))
