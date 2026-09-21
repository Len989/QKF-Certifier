"""Independent cold checking and application, without producer/search imports."""
import argparse
from pathlib import Path
import sys
import time
from .common import load_json, save_json, require, backend, digest, identity


def verify_record(case, route, saved, *, history=True, repetitions=1):
    from research.applicable_summary.audit import ExecutionGuard
    result, proof = saved['result'], saved['certificate']
    require(identity(saved) == saved['identity'], 'saved proof/result identity')
    require(result['status'] == case['expected'][route], 'registered status')
    started = time.perf_counter_ns()
    capability = None
    with ExecutionGuard(checking=True, witness=result['status'] == 'refuted') as guard:
        if proof is not None:
            if route.startswith(('sdk_', 'phase_')):
                from research.applicable_summary.checker import check
                capability = check(case['source'], case['request'], proof)
                actual = capability.result()
            elif route == 'retained':
                from research.unified.v6 import check
                actual = check(case['source'], case['request']['query']['requests'][0]['target'], proof)
            else:
                if route in ('direct41', 'query41'):
                    from research.source_query.checker import check
                else:
                    from research.source_planner.checker import check
                actual = check(case['source'], case['request']['query']['requests'][0], proof)
            require(actual == result, 'independent checked result differs')
        else:
            require(result['status'] in ('unsupported', 'budget_exhausted') or
                    (result['status'] == 'unresolved' and result.get('reason') == 'resource_budget'),
                    'missing semantic certificate')
    cold_ns, calls = time.perf_counter_ns() - started, guard.calls
    applied, warm_ns = [], None
    if capability is not None and result['status'] == 'certified':
        started = time.perf_counter_ns()
        with ExecutionGuard(checking=True, application=True):
            for _ in range(repetitions):
                for call in case['applications']:
                    value = capability.apply(call['input'], width=call.get('width'))
                    require(type(value) is type(call['output']) and value == call['output'], 'independent source-free apply')
                    applied.append(value)
        warm_ns = time.perf_counter_ns() - started
    n_history = 0
    begin_history = time.perf_counter_ns()
    if history:
        work = backend(saved)
        with ExecutionGuard(checking=True, witness=False):
            if route in ('direct41', 'query41') and 'prior_ground_evidence' in work:
                from research.source_query.checker import check
                previous = check(case['source'], case['request']['query']['requests'][0], work['prior_ground_evidence'])
                require(previous['status'] == 'unresolved', 'historical nonconsequence is not a source refutation')
                n_history += 1
            elif route in ('planner43', 'eager43'):
                from research.source_planner.checker import check
                for row in work.get('checkpoints', []):
                    require(digest(row['certificate']) == row['id'], 'historical obligation identity')
                    require(check(case['source'], case['request']['query']['requests'][0], row['certificate']) == row['result'],
                            'historical planner obligation')
                    n_history += 1
            elif route.startswith('sdk_') and work.get('foundations') is not None:
                from research.source_lemmas.checker import load_presentation
                from research.source_lemmas.context import scope
                context, _ = load_presentation(case['source'], case['request']['query'], work['foundations'])
                for row in work['checkpoints']:
                    require(row['id'] == digest(dict(scope=scope(context.context()), request=row['request'], item=row['item'])),
                            'historical E/E+ identity')
                    require(context.verify(row['request'], row['item']).result() == row['result'], 'historical E/E+ proof')
                    n_history += 1
    return dict(status='passed', packets=int(proof is not None), checkpoints=n_history,
                cold_check_ns=cold_ns, cold_check_calls=calls, warm_apply_ns=warm_ns,
                warm_apply_calls=len(applied), applied_sha256=digest(applied),
                application_status='measured' if warm_ns is not None else 'not_applicable',
                history_check_ns=time.perf_counter_ns() - begin_history,
                semantics=dict(result_sha256=digest(result), certificate_sha256=saved['identity']['certificate_sha256']))


def guarded_verify(case, route, saved, *, history=True, repetitions=1):
    from research.applicable_summary.replay import NoSearch
    guard = NoSearch()
    require(not guard.loaded(), 'fresh verifier has preloaded search modules')
    sys.meta_path.insert(0, guard)
    try:
        answer = verify_record(case, route, saved, history=history, repetitions=repetitions)
        require(not guard.loaded(), 'search imported during check/apply')
        answer.update(search_imports=0, timings_certified=False,
                      source_execution_for_positive_or_apply=False)
        return answer
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
