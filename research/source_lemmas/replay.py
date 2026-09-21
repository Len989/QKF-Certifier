"""Fresh verification of all foundations, goals and historical residuals."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from research.source_planner.replay import NoSearch as PreviousGuard


class NoSearch(PreviousGuard):
    def denies(self, name):
        return super().denies(name) or name in (
            'research.source_lemmas.fixtures', 'research.source_lemmas.experiment')


def run(root):
    guard = NoSearch()
    if guard.loaded():
        raise ValueError('fresh replay has preloaded search modules')
    sys.meta_path.insert(0, guard)
    try:
        from research.wordexpr.frontend import Unsupported
        from .context import load_json, digest, require, prepare, scope
        from .checker import check, load_presentation
        paths = list(root.rglob('*'))
        require(not root.is_symlink() and not any(p.is_symlink() for p in paths), 'artifact symlink')
        manifest = load_json(root / 'MANIFEST.json')
        require(type(manifest) is dict and set(manifest) ==
                {str(p.relative_to(root)) for p in paths if p.is_file()} - {'MANIFEST.json'}, 'artifact file set')
        for name, expected in manifest.items():
            p = Path(name)
            require(not p.is_absolute() and '..' not in p.parts, 'artifact path')
            require(hashlib.sha256((root / p).read_bytes()).hexdigest() == expected, 'artifact bytes')
        registration = load_json(Path(__file__).with_name('REGISTRATION.json'))
        protocol = load_json(root / 'PROTOCOL.json')
        require(registration == load_json(root / 'REGISTRATION.json') and
                protocol == load_json(Path(__file__).with_name('PROTOCOL.json')) and
                digest(protocol) == registration['protocol_sha256'], 'registered protocol/cases')
        routes = ('reuse', 'direct_cache', 'no_lemmas')
        counts, batches = {r: Counter() for r in routes}, {r: Counter() for r in routes}
        packets = checkpoints = requested = 0
        for entry in registration['cases']:
            folder = root / entry['name']
            case = load_json(folder / 'case.json')
            require(digest(case) == entry['case_sha256'], 'exact registered source/goals')
            attempts = []
            for route in routes:
                saved = load_json(folder / (route + '.json'))
                proof, result, work = saved['certificate'], saved['result'], saved['work']
                require(dict(status=result['status'], goals=[g['status'] for g in result['goals']]) == entry['expected'][route],
                        'registered outcome')
                if proof is not None:
                    require(result['status'] == 'completed' and check(case['source'], case['request'], proof) == result['goals'],
                            'portable foundations and independent consumers')
                    packets += 1
                else:
                    require(result['status'] in ('unsupported', 'budget_exhausted') and result['goals'] == [], 'missing complete proof')
                    if result['status'] == 'unsupported':
                        try:
                            prepare(case['source'], case['request'])
                        except Unsupported:
                            pass
                        else:
                            raise ValueError('unsupported disagrees with source admission')
                if work['foundations'] is not None:
                    context, _ = load_presentation(case['source'], case['request'], work['foundations'])
                    for row in work['checkpoints']:
                        require(row['id'] == digest(dict(scope=scope(context.context()), request=row['request'], item=row['item'])),
                                'historical obligation identity')
                        require(context.verify(row['request'], row['item']).result() == row['result'], 'historical E/E+ proof')
                        checkpoints += 1
                counts[route].update(g['status'] for g in result['goals'])
                batches[route][result['status']] += 1
                requested += len(case['request']['requests'])
                attempts.append(work['fact_attempts'])
            require(attempts[0] == attempts[1] == attempts[2], 'same native preparation')
        semantic = dict(cases=len(registration['cases']), routes=3, requested_goals=requested,
            packets=packets, checkpoints=checkpoints, batches={r: dict(v) for r, v in batches.items()},
            goals={r: dict(v) for r, v in counts.items()})
        require(load_json(root / 'SUMMARY.json')['semantic'] == semantic, 'semantic summary')
        require(load_json(root / 'FAILURES.json') == [], 'failed comparison')
        require(not guard.loaded(), 'search imported by cold checker')
        return dict(status='passed', semantic=semantic, search_imports=0,
                    telemetry_reexecuted=False, A2_timing_certified=False)
    finally:
        sys.meta_path.remove(guard)


if __name__ == '__main__':
    print(json.dumps(run(Path(sys.argv[1])), sort_keys=True))
