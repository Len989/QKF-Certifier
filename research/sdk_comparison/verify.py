"""Independent receiver: check packets, assess requests, export/explain and apply."""
import argparse
from pathlib import Path
import sys
import time
from .common import (load_json, save_json, require, identity, digest, canonical,
                     members, delivery, aggregate, queries, ENVELOPE)


def history_check(case, definitions, works):
    from research.applicable_summary.audit import ExecutionGuard
    count = 0
    with ExecutionGuard(checking=True):
        for (request, route), work in zip(definitions, works):
            backend = work.get('backend', work)
            if route in ('direct41', 'sdk_ordinary') and 'prior_ground_evidence' in backend:
                from research.source_query.checker import check
                old = check(case['source'], request['query']['requests'][0], backend['prior_ground_evidence'])
                require(old['status'] == 'unresolved', 'historical nonconsequence is not refutation')
                count += 1
            if backend.get('foundations') is not None:
                from research.source_lemmas.checker import load_presentation
                from research.source_lemmas.context import scope
                checked, _ = load_presentation(case['source'], request['query'], backend['foundations'])
                for row in backend['checkpoints']:
                    require(row['id'] == digest(dict(scope=scope(checked.context()), request=row['request'], item=row['item'])),
                            'historical obligation scope')
                    require(canonical(checked.verify(row['request'], row['item']).result()) == canonical(row['result']),
                            'historical E/E+ result')
                    count += 1
    return count


def verify_record(case, route, saved, *, history=True, repetitions=1):
    begin = time.perf_counter_ns()
    from research.applicable_summary.audit import ExecutionGuard
    require(identity(saved) == saved['identity'], 'delivery/result identity')
    result, envelope = saved['result'], saved['certificate']
    require(set(envelope) == {'schema', 'delivery', 'request_sha256', 'packets'}, 'delivery fields')
    require(envelope['schema'] == ENVELOPE and envelope['delivery'] == delivery(case, route), 'delivery kind')
    require(envelope['request_sha256'] == digest(case['request']), 'independent requests')
    definitions = members(case, route)
    require(type(envelope['packets']) is list and len(envelope['packets']) == len(definitions), 'complete member packets')
    require(set(result) == {'status', 'members'} and len(result['members']) == len(definitions), 'complete member results')
    require(result['status'] == aggregate(result['members']) == case['expected'][route], 'expected outcome')
    packets, capabilities, actual_results = 0, [], []
    for (request, backend), proof, claimed in zip(definitions, envelope['packets'], result['members']):
        capability = None
        with ExecutionGuard(checking=True, witness=claimed['status'] == 'refuted'):
            if proof is None:
                require(claimed['status'] in ('unsupported', 'budget_exhausted') or
                        (claimed['status'] == 'unresolved' and claimed.get('reason') == 'resource_budget'),
                        'missing semantic proof')
                actual = claimed  # Explicit nonsemantic budget/unsupported diagnostic.
            elif backend == 'direct41':
                from research.source_query.checker import check
                actual = check(case['source'], request['query']['requests'][0], proof)
                packets += 1
            else:
                from research.applicable_summary.checker import check
                capability = check(case['source'], request, proof)
                actual = capability.result()
                packets += 1
            require(canonical(actual) == canonical(claimed), 'independent member result')
        actual_results.append(actual)
        capabilities.append(capability)
    cold_ns = time.perf_counter_ns() - begin
    answers, followups, exported = [], [], []
    begin = time.perf_counter_ns()
    with ExecutionGuard(checking=True, application=True):
        if delivery(case, route) == 'consumer_service':
            require(len(capabilities) == 1 and capabilities[0] is not None, 'service needs one checked module')
            for request in queries(case):
                answer = capabilities[0].assess(request)
                require(answer['status'] == 'certified', 'service consumer not established')
                answers.append(answer)
        for f in case['followups']:
            answer = capabilities[0].assess(f['request'])
            require((answer['status'], answer['reason']) == (f['status'], f['reason']), 'independent follow-up outcome')
            followups.append(answer)
    assess_ns = time.perf_counter_ns() - begin
    begin = time.perf_counter_ns()
    with ExecutionGuard(checking=True, application=True):
        for cap, proof in zip(capabilities, envelope['packets']):
            if cap is not None:
                exported_packet = cap.export()
                require(canonical(exported_packet) == canonical(proof), 'SDK export differs from received packet')
                explanation = cap.explain(consumer=queries(case)[-1]) if delivery(case, route) == 'consumer_service' else cap.explain()
                require(explanation['source_sha256'] == cap.result()['source_sha256'], 'explanation source binding')
                if delivery(case, route) == 'consumer_service':
                    require(explanation['sufficiency']['status'] == 'certified', 'explanation consumer')
                exported.append(dict(packet_sha256=digest(exported_packet), explanation_sha256=digest(explanation)))
    export_ns = time.perf_counter_ns() - begin
    applied = []
    begin = time.perf_counter_ns()
    with ExecutionGuard(checking=True, application=True):
        for cap in capabilities:
            if cap is None or cap.result()['status'] != 'certified':
                continue
            for _ in range(repetitions):
                for call in case['applications']:
                    value = cap.apply(call['input'], width=call.get('width'))
                    require(type(value) is type(call['output']) and value == call['output'], 'independent application')
                    applied.append(value)
    apply_ns = time.perf_counter_ns() - begin if applied else None
    if history:
        require(type(saved['work'].get('members')) is list and len(saved['work']['members']) == len(definitions),
                'complete intermediate-history member list')
    checkpoints = history_check(case, definitions, saved['work']['members']) if history else 0
    semantic = dict(packets=packets, results_sha256=digest(actual_results), answers=answers, followups=followups,
                    exports=exported, application_count=len(applied), applications_sha256=digest(applied))
    return dict(status='passed', packets=packets, checkpoints=checkpoints, cold_check_ns=cold_ns,
                assess_ns=assess_ns, export_explain_ns=export_ns, warm_apply_ns=apply_ns,
                warm_apply_calls=len(applied), semantic=semantic, application_status='measured' if applied else 'not_applicable',
                lifecycle_receiver_ns=cold_ns + assess_ns + export_ns)


def guarded_verify(case, route, saved, *, history=True, repetitions=1):
    from research.applicable_summary.replay import NoSearch
    guard = NoSearch()
    require(not guard.loaded(), 'fresh verifier needs no search modules')
    sys.meta_path.insert(0, guard)
    try:
        result = verify_record(case, route, saved, history=history, repetitions=repetitions)
        require(not guard.loaded(), 'search imported during receiver operations')
        return dict(result, search_imports=0, source_execution_for_positive_or_apply=False, timings_certified=False)
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
