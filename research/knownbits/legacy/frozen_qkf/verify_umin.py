#!/usr/bin/env python3
"""Replay one saved component or whole proof, without producer search."""
import argparse
import json
import sys
from pathlib import Path
from audit_fixed import validate_freeze
ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', type=Path, required=True)
    ap.add_argument('--operator', required=True)
    ap.add_argument('--entry', default='solution')
    ap.add_argument('--target', required=True)
    ap.add_argument('--results', type=Path, default=ROOT / 'results')
    args = ap.parse_args(); repo = args.repo.resolve(); validate_freeze(repo)
    sys.path[:0] = [str(repo / 'src'), str(repo / 'tests')]
    from prove_umin import verify_component, verify_whole
    source = (ROOT / 'fixtures/corpus' / args.operator / 'solution.mlir').read_text()
    bundle = {'program': source}
    if 'func.call @meet(' in source: bundle['meet'] = (ROOT / 'fixtures/helpers/meet.mlir').read_text()
    if 'func.call @getTop(' in source: bundle['top'] = (ROOT / 'fixtures/helpers/top.mlir').read_text()
    if args.entry == 'solution':
        manifest = json.loads((args.results / 'certificates' / (args.operator + '__whole.json')).read_text())
        certs = {e: json.loads((args.results / path).read_text()) for e, path in manifest['components'].items()}
        n = verify_whole(bundle, manifest, certs, args.target)
    else:
        cert = json.loads((args.results / 'certificates' / (args.operator + '__' + args.entry + '.json')).read_text())
        n = verify_component(bundle, args.entry, cert, args.target)
    print(json.dumps({'status': 'PASS', 'operator': args.operator, 'entry': args.entry,
                      'target': args.target, 'widths': 'all positive', 'checked_transitions': n}, indent=2))


if __name__ == '__main__': main()
