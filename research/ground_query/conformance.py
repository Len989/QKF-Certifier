"""Registered finite-ground conformance, not a source-inference speed benchmark."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from .checker import check
from .fixtures import registered_cases
from .producer import prove, search
from .schema import digest, load_json, require, save_json


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    registration = load_json(Path(__file__).with_name('REGISTRATION.json'))
    save_json(root / 'REGISTRATION.json', registration)
    save_json(root / 'PROTOCOL.json', load_json(Path(__file__).with_name('PROTOCOL.json')))
    cases, diagnostics = [], []
    start = time.perf_counter()
    try:
        for meta, request in registered_cases():
            entry = dict(meta, request_sha256=digest(request))
            require(entry == registration['cases'][len(cases)], 'registered input changed')
            folder = root / entry['name']
            folder.mkdir()
            save_json(folder / 'request.json', request)
            begin = time.perf_counter()
            certificate, stats = prove(request, entry['mode'], entry['horizon'])
            produced = time.perf_counter()
            checked = check(request, certificate)
            end = time.perf_counter()
            save_json(folder / 'certificate.json', certificate)
            save_json(folder / 'checked.json', checked)
            cases.append(entry)
            diagnostics.append({'name': entry['name'], 'producer_seconds': produced - begin,
                                'checker_seconds': end - produced, 'stats': stats})
            if len(cases) % 25 == 0:
                print(f'ground-query certificates: {len(cases)}', file=sys.stderr, flush=True)
        require(cases == registration['cases'], 'incomplete registered population')
        save_json(root / 'CASES.json', cases)
        reference = subprocess.run([sys.executable, '-m', 'research.ground_query.reference', str(root)],
                                   capture_output=True, text=True, timeout=300)
        (root / 'reference.stdout').write_text(reference.stdout)
        (root / 'reference.stderr').write_text(reference.stderr)
        require(reference.returncode == 0, 'full-layer reference failed: ' + reference.stderr[-1000:])
        ref = load_json(root / 'REFERENCE.json')
        pair_checks, horizons = 0, 0
        for entry in cases:
            request = load_json(root / entry['name'] / 'request.json')
            inp, terms, result = search(request)
            for d, level in enumerate(ref[entry['name']]):
                active = [i for i in range(len(terms)) if inp.depths[i] <= d]
                if entry['family'] == 'catalan':
                    require(level['pool_size'] == len(active), 'Catalan bounded layer not covered')
                for pos, i in enumerate(active):
                    for j in active[pos:]:
                        require(result.same_at(terms[i], terms[j], d) ==
                                (level['labels'][i] == level['labels'][j]), 'reference partition differs')
                        pair_checks += 1
                horizons += 1
        from .reference import rewrite_gap
        gap_result = rewrite_gap()
        require(gap_result == {'congruence': 2, 'sequential_rewrite': 3}, 'strict gap differs')
        # Recompute all semantic summaries from certificates, not producer receipts.
        from .replay import semantic_summary
        summary = {'schema': 'qkf-ground-query-conformance-summary-v1', 'status': 'passed',
                   'semantic': semantic_summary(root, cases),
                   'reference': {'cases': len(cases), 'horizons': horizons,
                                 'pair_horizon_comparisons': pair_checks, 'strict_gap': gap_result},
                   'scope': 'finite-ground development conformance; no source speedup or new Lean theorem'}
        save_json(root / 'SUMMARY.json', summary)
        (root / 'PERFORMANCE.json').write_text(json.dumps({'python': sys.version,
            'elapsed_seconds': time.perf_counter() - start, 'cases': diagnostics}, sort_keys=True) + '\n')
        save_json(root / 'FAILURES.json', [])
        manifest = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(root.rglob('*')) if p.is_file()}
        save_json(root / 'MANIFEST.json', manifest)
        return summary
    except Exception as error:
        save_json(root / 'FAILURES.json', [{'completed_cases': len(cases), 'error': str(error)}])
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    print(json.dumps(run(parser.parse_args().output), sort_keys=True))
