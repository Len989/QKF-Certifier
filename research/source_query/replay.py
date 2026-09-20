"""Independent portable replay; no producer, native discovery, CC search or SMT."""
import hashlib
import importlib.abc
import json
from pathlib import Path
import sys
from collections import Counter


class NoSearch(importlib.abc.MetaPathFinder):
    blocked = ('research.source_query.producer', 'research.source_query.facts',
               'research.source_query.ordinary', 'research.source_query.experiment',
               'research.source_query.fixtures', 'research.ground_query.producer',
               'research.ground_query.prototype', 'research.ground_query.reference',
               'research.ground_query.conformance', 'z3', 'cvc5', 'subprocess')

    def __init__(self, native_only=False):
        self.native_only = native_only

    def denies(self, name):
        return (name.endswith('.producer') or any(name == p or name.startswith(p + '.') for p in self.blocked)
                or (self.native_only and name.startswith(('research.signed_coverage', 'research.signed_runtime',
                    'research.signed_targets', 'research.signed_observations', 'research.signed_context'))))

    def loaded(self):
        return sorted(name for name in sys.modules if self.denies(name))

    def find_spec(self, fullname, path=None, target=None):
        if self.denies(fullname):
            raise ImportError('source replay forbids ' + fullname)
        return None


def run(root):
    guard = NoSearch()
    if guard.loaded():
        raise ValueError('fresh replay requires no preloaded search modules')
    sys.meta_path.insert(0, guard)
    try:
        from .context import load_json, digest, require, prepare
        from .checker import check
        from research.wordexpr.frontend import Unsupported
        paths = list(root.rglob('*'))
        require(not any(p.is_symlink() for p in paths), 'artifact symlink')
        manifest = load_json(root / 'MANIFEST.json')
        require(type(manifest) is dict and set(manifest) ==
                {str(p.relative_to(root)) for p in paths if p.is_file()} - {'MANIFEST.json'}, 'artifact file set')
        for name, expected in manifest.items():
            p = Path(name)
            require(not p.is_absolute() and '..' not in p.parts, 'artifact path')
            require(hashlib.sha256((root / p).read_bytes()).hexdigest() == expected, 'artifact bytes')
        registration = load_json(Path(__file__).with_name('REGISTRATION.json'))
        require(registration == load_json(root / 'REGISTRATION.json'), 'exact registration')
        require(load_json(root / 'PROTOCOL.json') == load_json(Path(__file__).with_name('PROTOCOL.json')), 'exact protocol')
        counts, certificates, native_facts = Counter(), 0, 0
        for entry in registration['cases']:
            folder = root / entry['name']
            case = load_json(folder / 'case.json')
            require(digest(case) == entry['case_sha256'], 'registered source/query/options')
            ground_hashes = []
            for route in ('query', 'ordinary'):
                saved = load_json(folder / (route + '.json'))
                proof, result, work = saved['certificate'], saved['result'], saved['work']
                require(result['status'] == entry['expected'], 'registered outcome')
                if proof is not None:
                    require(check(case['source'], case['request'], proof) == result, 'consumer receipt differs')
                    certificates += 1
                    native_facts += result.get('checked_native_facts', 0)
                else:
                    require(result['status'] in ('unsupported', 'budget_exhausted'), 'missing semantic proof')
                    if result['status'] == 'unsupported':
                        try:
                            prepare(case['source'], case['request'])
                        except Unsupported:
                            pass
                        else:
                            raise ValueError('unsupported receipt does not match source admission')
                if 'prior_ground_evidence' in work:
                    prior = check(case['source'], case['request'], work['prior_ground_evidence'])
                    require(prior['status'] == 'unresolved' and not prior['source_refutation'], 'prior abstract obligation')
                # Telemetry is integrity-bound, not a trusted execution certificate.
                ground_hashes.append(work['ground_request_sha256'])
                counts[result['status']] += 1
            require(ground_hashes[0] == ground_hashes[1], 'controls did not receive identical finite E/O')
        semantic = {'cases': len(registration['cases']), 'routes': 2, 'certificates': certificates,
                    'checked_native_facts': native_facts, 'statuses': dict(counts)}
        require(load_json(root / 'FAILURES.json') == [], 'recorded failure')
        require(load_json(root / 'SUMMARY.json')['semantic'] == semantic, 'saved semantic summary')
        require(not guard.loaded(), 'search module imported by replay')
        return {'status': 'passed', 'semantic': semantic, 'search_imports': 0,
                'telemetry_reexecuted': False, 'unresolved_diagnostics_reexecuted': False}
    finally:
        sys.meta_path.remove(guard)


if __name__ == '__main__':
    print(json.dumps(run(Path(sys.argv[1])), sort_keys=True))
