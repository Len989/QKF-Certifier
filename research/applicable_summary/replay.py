"""Fresh checker/application process; block search imports before loading SDK."""
import hashlib
import importlib.abc
import json
from pathlib import Path
import sys


class NoSearch(importlib.abc.MetaPathFinder):
    prefixes = ('z3', 'cvc5', 'research.source_planner.language', 'research.source_planner.native',
                'research.source_query.facts', 'research.source_query.ordinary',
                'research.source_forcing.native', 'research.source_forcing.direct',
                'research.ground_query.prototype', 'research.ground_query.reference',
                'research.pure_rows.reference')

    def denies(self, name):
        return (name.endswith(('.producer', '_producer', '.fixtures', '.experiment', '.conformance'))
                or any(name == p or name.startswith(p + '.') for p in self.prefixes))

    def loaded(self):
        return sorted(n for n in sys.modules if self.denies(n))

    def find_spec(self, fullname, path=None, target=None):
        if self.denies(fullname):
            raise ImportError('summary replay forbids ' + fullname)
        return None


def run(root):
    guard = NoSearch()
    if guard.loaded():
        raise ValueError('replay needs a fresh process without search modules')
    sys.meta_path.insert(0, guard)
    try:
        from .contract import load_json, require, digest
        from .checker import check
        from .audit import ExecutionGuard
        from collections import Counter
        paths = list(root.rglob('*'))
        require(not root.is_symlink() and not any(p.is_symlink() for p in paths), 'artifact symlink')
        manifest = load_json(root / 'MANIFEST.json')
        require(type(manifest) is dict and set(manifest) ==
                {str(p.relative_to(root)) for p in paths if p.is_file()} - {'MANIFEST.json'}, 'artifact file set')
        for name, expected in manifest.items():
            p = Path(name)
            require(not p.is_absolute() and '..' not in p.parts, 'artifact path')
            require(hashlib.sha256((root / p).read_bytes()).hexdigest() == expected, 'artifact bytes')
        reg = load_json(root / 'REGISTRATION.json')
        require(reg == load_json(Path(__file__).with_name('REGISTRATION.json')), 'exact registered cases')
        protocol = load_json(root / 'PROTOCOL.json')
        require(protocol == load_json(Path(__file__).with_name('PROTOCOL.json')) and digest(protocol) == reg['protocol_sha256'], 'protocol')
        counts, packets, applications = Counter(), 0, 0
        for entry in reg['cases']:
            folder = root / entry['name']
            case, saved = load_json(folder / 'case.json'), load_json(folder / 'outcome.json')
            require(digest(case) == entry['case_sha256'], 'registered source and consumer')
            proof, result = saved['certificate'], saved['result']
            require(result['status'] == entry['expected'], 'registered status')
            if proof is not None:
                with ExecutionGuard(checking=True, witness=result['status'] == 'refuted'):
                    checked = check(case['source'], case['request'], proof)
                require(checked.result() == result, 'portable summary result')
                actual = []
                with ExecutionGuard(checking=True, application=True):
                    for call in case['applications']:
                        value = checked.apply(call['input'], width=call.get('width'))
                        require(type(value) is type(call['output']) and value == call['output'], 'source-free application')
                        actual.append(value); applications += 1
                    checked.explain()
                require(actual == [v['value'] for v in load_json(folder / 'applications.json')], 'saved applications')
                packets += 1
            else:
                require(result['status'] == 'unsupported' or (result['status'] == 'unresolved' and result['reason'] == 'resource_budget'), 'missing proof')
            counts[result['status']] += 1
        semantic = dict(cases=len(reg['cases']), packets=packets, applications=applications, statuses=dict(counts))
        require(load_json(root / 'SUMMARY.json')['semantic'] == semantic and load_json(root / 'FAILURES.json') == [], 'semantic summary')
        require(not guard.loaded(), 'search import during check/apply/explain')
        return dict(status='passed', semantic=semantic, search_imports=0, source_execution_for_positive_or_apply=False,
                    search_budget_diagnostics_reexecuted=False, timings_certified=False)
    finally:
        sys.meta_path.remove(guard)


if __name__ == '__main__':
    print(json.dumps(run(Path(sys.argv[1])), sort_keys=True))
