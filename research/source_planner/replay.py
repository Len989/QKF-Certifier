"""Fresh replay of consumer proofs and scoped historical models, no planner."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from research.source_query.replay import NoSearch as PreviousGuard


class NoSearch(PreviousGuard):
    def denies(self, name):
        return super().denies(name) or name in (
            'research.source_planner.language', 'research.source_planner.native',
            'research.source_planner.fixtures', 'research.source_planner.experiment')


def run(root):
    guard = NoSearch()
    if guard.loaded():
        raise ValueError('fresh process has preloaded planner/search modules')
    sys.meta_path.insert(0, guard)
    try:
        from research.wordexpr.frontend import Unsupported
        from .context import prepare, digest, load_json, require
        from .checker import check
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
        require(registration == load_json(root / 'REGISTRATION.json'), 'registration identity')
        protocol = load_json(root / 'PROTOCOL.json')
        require(protocol == load_json(Path(__file__).with_name('PROTOCOL.json')) and digest(protocol) == registration['protocol_sha256'], 'protocol identity')
        routes = ('planner', 'ordinary', 'eager')
        counts, certificates, checkpoints = {r: Counter() for r in routes}, 0, 0
        for entry in registration['cases']:
            folder = root / entry['name']
            case = load_json(folder / 'case.json')
            require(digest(case) == entry['case_sha256'], 'source/request/budget identity')
            attempts = []
            for route in routes:
                saved = load_json(folder / (route + '.json'))
                cert, result, work = saved['certificate'], saved['result'], saved['work']
                require(result['status'] == entry['expected'][route], 'registered outcome')
                if cert is not None:
                    require(check(case['source'], case['request'], cert) == result, 'consumer evidence')
                    certificates += 1
                else:
                    require(result['status'] in ('unsupported', 'budget_exhausted'), 'missing semantic proof')
                    if result['status'] == 'unsupported':
                        try:
                            prepare(case['source'], case['request'])
                        except Unsupported:
                            pass
                        else:
                            raise ValueError('unsupported diagnostic disagrees with admission')
                for prior in work['checkpoints']:
                    require(digest(prior['certificate']) == prior['id'], 'historical E identity')
                    require(check(case['source'], case['request'], prior['certificate']) == prior['result'], 'historical proof is scoped to its E')
                    checkpoints += 1
                if route in routes[:2]:
                    attempts.append(work['fact_attempts'])
                counts[route][result['status']] += 1
            require(attempts[0] == attempts[1], 'identical adaptive native preparation')
        semantic = dict(cases=len(registration['cases']), routes=3, certificates=certificates,
                        checkpoints=checkpoints, statuses={r: dict(c) for r, c in counts.items()})
        require(load_json(root / 'SUMMARY.json')['semantic'] == semantic, 'semantic summary')
        require(load_json(root / 'FAILURES.json') == [], 'recorded failed run')
        require(not guard.loaded(), 'planner/search imported by checker')
        return dict(status='passed', semantic=semantic, search_imports=0,
                    telemetry_reexecuted=False, search_exhaustion_certified=False)
    finally:
        sys.meta_path.remove(guard)


if __name__ == '__main__':
    print(json.dumps(run(Path(sys.argv[1])), sort_keys=True))
