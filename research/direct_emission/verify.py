"""Unchanged PR47 receiver plus a ban on the new search entry points."""
import argparse
from pathlib import Path
import sys
from research.applicable_summary.replay import NoSearch as Previous
from research.sdk_comparison.verify import verify_record
from .common import require, save_json, load_json


class NoSearch(Previous):
    prefixes = Previous.prefixes + ('research.prepared_context.query',
                                    'research.prepared_context.ordinary',
                                    'research.prepared_context.sdk',
                                    'research.direct_emission.sdk', 'research.direct_emission.export')


def guarded_verify(case, route, saved, *, history=True, repetitions=64):
    guard = NoSearch()
    require(not guard.loaded(), 'fresh receiver required')
    sys.meta_path.insert(0, guard)
    try:
        result = verify_record(case, route, saved, history=history, repetitions=repetitions)
        require(not guard.loaded(), 'search imported during receiver operations')
        return dict(result, search_imports=0, source_execution_for_positive_or_apply=False,
                    timings_certified=False)
    finally:
        sys.meta_path.remove(guard)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', type=Path)
    parser.add_argument('route')
    parser.add_argument('saved', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--history', action='store_true')
    parser.add_argument('--repetitions', type=int, default=64)
    args = parser.parse_args()
    save_json(args.output, guarded_verify(load_json(args.case), args.route, load_json(args.saved),
                                         history=args.history, repetitions=args.repetitions))
