"""Fresh replay with producer/search imports blocked before the checker loads."""
from collections import Counter
import hashlib
import importlib.abc
import json
from pathlib import Path
import sys


class NoSearch(importlib.abc.MetaPathFinder):
    blocked = ('research.source_forcing.producer', 'research.source_forcing.native',
               'research.source_forcing.direct', 'research.source_forcing.fixtures',
               'research.source_forcing.experiment', 'research.pure_rows.producer',
               'research.pure_rows.reference', 'research.graal.carry_producer',
               'research.graal.lower_producer', 'research.signed_coverage',
               'research.signed_runtime', 'z3', 'cvc5')

    def denies(self, name):
        return name.endswith(('.producer', '_producer')) or any(name == p or name.startswith(p + '.') for p in self.blocked)

    def loaded(self):
        return sorted(n for n in sys.modules if self.denies(n))

    def find_spec(self, fullname, path=None, target=None):
        if self.denies(fullname):
            raise ImportError('local forcing replay forbids ' + fullname)
        return None


def run(root):
    guard = NoSearch()
    if guard.loaded():
        raise ValueError('fresh replay requires no preloaded search modules')
    sys.meta_path.insert(0, guard)
    try:
        from .context import Unsupported, digest, need, prepare, read_json
        from .audit import Audit
        from .checker import check
        paths = list(root.rglob('*'))
        need(not root.is_symlink() and not any(p.is_symlink() for p in paths), 'artifact symlink')
        manifest = read_json(root / 'MANIFEST.json')
        need(type(manifest) is dict and set(manifest) ==
             {str(p.relative_to(root)) for p in paths if p.is_file()} - {'MANIFEST.json'}, 'artifact file set')
        for name, expected in manifest.items():
            p = Path(name)
            need(not p.is_absolute() and '..' not in p.parts, 'artifact path')
            need(hashlib.sha256((root / p).read_bytes()).hexdigest() == expected, 'artifact bytes')
        registration = read_json(Path(__file__).with_name('REGISTRATION.json'))
        need(registration == read_json(root / 'REGISTRATION.json'), 'exact registration')
        protocol = read_json(root / 'PROTOCOL.json')
        need(protocol == read_json(Path(__file__).with_name('PROTOCOL.json')) and digest(protocol) == registration['protocol_sha256'], 'registered protocol')
        routes = ('forcing', 'no_saturation', 'direct_seeds', 'direct_cell')
        counts, certificates = {r: Counter() for r in routes}, 0
        for entry in registration['cases']:
            folder = root / entry['name']
            case = read_json(folder / 'case.json')
            need(digest(case) == entry['case_sha256'], 'registered source/request/options')
            hashes = []
            for route in routes:
                saved = read_json(folder / (route + '.json'))
                cert, result = saved['certificate'], saved['result']
                need(result['status'] == entry['expected'][route], 'registered result status')
                if cert is not None:
                    with Audit('replay'):
                        need(check(case['source'], case['request'], cert) == result, 'consumer proof differs')
                    certificates += 1
                else:
                    need(result['status'] in ('unsupported', 'budget_exhausted'), 'missing proof')
                    if result['status'] == 'unsupported':
                        with Audit('replay'):
                            try:
                                prepare(case['source'], case['request'])
                            except Unsupported:
                                pass
                            else:
                                raise ValueError('unsupported diagnostic contradicted by admission')
                if route != 'direct_cell':
                    hashes.append(saved['work']['preparation_sha256'])
                counts[route][result['status']] += 1
            need(len(set(hashes)) == 1, 'same-seed preparation hash')
        semantic = dict(cases=len(registration['cases']), routes=len(routes), certificates=certificates,
                        statuses={r: dict(c) for r, c in counts.items()})
        need(read_json(root / 'SUMMARY.json')['semantic'] == semantic, 'saved semantic summary')
        need(read_json(root / 'FAILURES.json') == [], 'recorded failure')
        need(not guard.loaded(), 'checker imported search')
        return dict(status='passed', semantic=semantic, search_imports=0, telemetry_reexecuted=False,
                    budget_search_reexecuted=False)
    finally:
        sys.meta_path.remove(guard)


if __name__ == '__main__':
    print(json.dumps(run(Path(sys.argv[1])), sort_keys=True))
