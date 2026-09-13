#!/usr/bin/env python3
"""Apply checked observer identities uniformly after the frozen audit."""
import argparse
import collections
import json
import pickle
import sys
from pathlib import Path
from prefix_masks import lower, supported, allowed_node, RUNS, BACKEND
from regular_interfaces import order

ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', type=Path, required=True)
    ap.add_argument('--results', type=Path, default=ROOT / 'results')
    args = ap.parse_args(); out = args.results
    from audit_fixed import validate_freeze
    repo=args.repo.resolve();validate_freeze(repo);sys.path.insert(0,str(repo/'src'))
    from observer_kernel import produce,replay,EXTENSION
    with (out / 'local_cache.pkl').open('rb') as f: items = pickle.load(f)
    records = []
    for item in items:
        r = item['record']
        if 'regular_without_prefix' not in r:
            r['regular_without_prefix'] = r['regular_after']
        r['regular_without_observers']=supported(item['simple'])
        observed,trace=produce(item['simple'],2)
        assert replay(item['simple'],trace,observed,2)==observed
        item['observed']=observed;item['observer_trace']=trace
        r['observer_rewrites']=len(trace)
        r['observer_rules']=dict(collections.Counter(t['rule'] for t in trace))
        nodes = order(lower(observed))
        r['regular_after'] = supported(observed)
        r['blockers'] = dict(collections.Counter(t[0] for t in nodes if not allowed_node(t)))
        r['run_nodes'] = dict(collections.Counter(t[0] for t in nodes if t[0] in RUNS))
        if r['regular_without_observers'] and not r['regular_after']:
            raise AssertionError('existing fragment lost')
        records.append(r)
    summary = {}
    for role in ('solution', 'body', 'component'):
        rs = [r for r in records if r['role'] == role]
        summary[role] = dict(total=len(rs), regular_without_prefix=sum(r['regular_without_prefix'] for r in rs),
                            regular_without_observers=sum(r['regular_without_observers'] for r in rs),
                            regular_with_observers=sum(r['regular_after'] for r in rs),
                            with_supported_target=sum(r['regular_after'] and r['target'] is not None for r in rs))
    result = {'backend': BACKEND,'extension':EXTENSION,'summary': summary, 'records': records,
              'scope': 'Exact syntactic compilation coverage, separate from correctness.'}
    (out / 'observer_audit.json').write_text(json.dumps(result, indent=2) + '\n')
    with (out / 'local_cache.pkl').open('wb') as f: pickle.dump(items, f)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__': main()
