"""Fresh-process replay with search/prototype imports forbidden before loading checker."""

import hashlib
import importlib.abc
import json
from pathlib import Path
import sys
from collections import Counter


class NoSearch(importlib.abc.MetaPathFinder):
    blocked = ('research.ground_query.producer', 'research.ground_query.prototype',
                   'research.ground_query.conformance', 'research.ground_query.reference',
                   'research.ground_query.fixtures', 'engine', 'visibility_cc',
                   'visibility_cc_fast', 'certificates', 'countermodel', 'papers',
                   'z3', 'cvc5', 'subprocess')

    def denies(self, fullname):
        return any(fullname == name or fullname.startswith(name + '.') for name in self.blocked)

    def loaded(self):
        return sorted(name for name in sys.modules if self.denies(name))

    def find_spec(self, fullname, path=None, target=None):
        if self.denies(fullname):
            raise ImportError('semantic replay forbids ' + fullname)
        return None


def semantic_summary(root, cases):
    from .checker import check
    from .schema import canonical, digest, load_json, parse, require
    counts, statuses, profiles = Counter(), Counter(), Counter()
    goals, proof_bytes, events, models = 0, 0, 0, 0
    named = {}
    for case in cases:
        name = case['name']
        require(type(name) is str and Path(name).name == name, 'case name')
        folder = root / name
        request = load_json(folder / 'request.json')
        require(digest(request) == case['request_sha256'], 'case request binding')
        certificate = load_json(folder / 'certificate.json')
        result = check(request, certificate)
        require(result == load_json(folder / 'checked.json'), 'replay differs: ' + name)
        require(result['mode'] == case['mode'] and result['horizon'] ==
                (result['final_horizon'] if case['horizon'] is None else case['horizon']), 'registered mode')
        counts[case['family']] += 1
        goals += len(result['goals'])
        proof_bytes += len(canonical(certificate))
        events += len(certificate['events'])
        models += len(certificate['models'])
        statuses.update(g['status'] for g in result['goals'])
        if case['family'] == 'catalan':
            inp = parse(request)
            h = len(case['expected_profile'])
            # Completeness of T^h in this unary signature is checked by cardinality
            # at every depth, plus unique syntactic nodes enforced by the schema.
            require(inp.sorts == ('A',) and inp.signature['f'] == {'args': ['A'], 'result': 'A'}, 'unary family')
            require(all(op == 'f' or spec == {'args': [], 'result': 'A'}
                        for op, spec in inp.signature.items()), 'extra family symbol')
            constants = len(inp.signature) - 1
            require(Counter(inp.depths) == Counter({d: constants for d in range(h + 1)}), 'full term layers')
            require(len(inp.queries) == len(inp.nodes) * (len(inp.nodes) + 1) // 2 and
                    len({tuple(sorted(pair)) for pair in inp.queries}) == len(inp.queries), 'full pair coverage')
            profile = []
            for d in range(h + 1):
                profile.append(max([d] + [g['exact_threshold'] for (a, b), g in zip(inp.queries, result['goals'])
                    if max(inp.depths[a], inp.depths[b]) <= d and g['status'] == 'equal']))
            require(profile == case['expected_profile'] + [h], 'Catalan layer profile differs')
            profiles[h] += 1
        else:
            named[name] = result['goals']
    require(counts == {'named': 8, 'catalan': 195} and profiles == {1: 2, 2: 5, 3: 14, 4: 42, 5: 132},
            'registered development denominator')
    require(named['gap'][0]['exact_threshold'] == 2 and
            named['flattened'][0]['exact_threshold'] == 1, 'presentation visibility changed')
    # The shared typed interface contains 8 named observations and every pair.
    request = load_json(root / 'shared_typed' / 'request.json')
    observed = sorted({i for pair in request['queries'] for i in pair})
    sizes = []
    for horizon in (1, 2):
        parent = {i: i for i in observed}
        def find(i):
            while parent[i] != i:
                i = parent[i]
            return i
        for (a, b), goal in zip(request['queries'], named['shared_typed']):
            if goal['status'] == 'equal' and goal['exact_threshold'] <= horizon:
                parent[find(a)] = find(b)
        sizes.append(len({find(i) for i in observed}))
    require(sizes == [5, 3], 'typed N1/N2')
    return {'certificates': len(cases), 'families': dict(counts), 'catalan_profiles': {str(k): v for k, v in profiles.items()},
            'checked_goals': goals, 'statuses': dict(statuses), 'certificate_bytes': proof_bytes,
            'proof_events': events, 'models': models, 'typed_interface_classes': sizes}


def run(root):
    guard = NoSearch()
    # Meta-path hooks alone cannot reject a dependency already in sys.modules.
    if guard.loaded():
        raise ValueError('fresh replay requires no preloaded search modules')
    sys.meta_path.insert(0, guard)
    try:
        from .checker import check
        from .schema import load_json, require
        inventory = load_json(root / 'MANIFEST.json')
        require(type(inventory) is dict, 'manifest shape')
        paths = list(root.rglob('*'))
        require(not any(p.is_symlink() for p in paths), 'artifact symlink')
        require({str(p.relative_to(root)) for p in paths if p.is_file()} - {'MANIFEST.json'} == set(inventory),
                'artifact file set differs')
        for name, expected in inventory.items():
            path = Path(name)
            require(not path.is_absolute() and '..' not in path.parts, 'manifest path')
            require(hashlib.sha256((root / path).read_bytes()).hexdigest() == expected, 'artifact hash mismatch: ' + name)
        cases = load_json(root / 'CASES.json')
        registered = load_json(Path(__file__).with_name('REGISTRATION.json'))
        require(load_json(root / 'REGISTRATION.json') == registered and cases == registered['cases'], 'registration binding')
        require(load_json(root / 'PROTOCOL.json') == load_json(Path(__file__).with_name('PROTOCOL.json')), 'protocol binding')
        result = semantic_summary(root, cases)
        require(result == load_json(root / 'SUMMARY.json')['semantic'], 'saved summary is not evidence')
        require(load_json(root / 'FAILURES.json') == [], 'failed conformance artifact')
        search_imports = len(guard.loaded())
        require(search_imports == 0, 'search module loaded during replay')
        return {'status': 'passed', **result, 'producer_imports': search_imports,
                'reference_rerun': False, 'summary_sha256': hashlib.sha256((root / 'SUMMARY.json').read_bytes()).hexdigest()}
    finally:
        sys.meta_path.remove(guard)


if __name__ == '__main__':
    print(json.dumps(run(Path(sys.argv[1])), sort_keys=True))
