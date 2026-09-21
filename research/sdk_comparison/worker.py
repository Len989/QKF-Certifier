"""Fresh composition of unchanged producers and SDK adapters."""
import argparse
from contextlib import nullcontext
from pathlib import Path
import time
import tracemalloc
from .common import (canonical, digest, save_json, load_json, require, identity,
                     members, delivery, aggregate, ENVELOPE)


def produce(source, request, limits, route):
    if route in ('direct41', 'sdk_ordinary'):
        from research.source_query.producer import prove
        from research.source_query.audit import DEFAULTS
        proof, result, work = prove(source, request['query']['requests'][0], route='ordinary',
                                   limits={k: v for k, v in limits.items() if k in DEFAULTS})
        if route == 'direct41':
            return proof, result, work
        started = time.perf_counter_ns()
        if proof is None:
            from research.applicable_summary.contract import RESULT
            result = dict(schema=RESULT, profile=request['profile'], applicable=False, goals=[],
                          status='unsupported' if result['status'] == 'unsupported' else 'unresolved',
                          reason=result.get('reason', 'unsupported') if result['status'] == 'unsupported' else 'resource_budget',
                          backend_result=result)
        else:
            from research.applicable_summary.checker import from_certificate
            from research.applicable_summary.audit import ExecutionGuard
            with ExecutionGuard(checking=True, witness=result['status'] == 'refuted'):
                proof, result = from_certificate(source, request, proof, kind='source_query')
        return proof, result, dict(backend=work, phases=dict(native_import_ns=time.perf_counter_ns() - started),
                                   history_kind='source_query')
    from research.applicable_summary.producer import build
    name = dict(sdk_default='no_lemmas', sdk_reuse='reuse', sdk_direct='direct_cache').get(route)
    if name is None:
        require(route.startswith('phase_'), 'unknown producer route')
        name = route[len('phase_'):]
    return build(source, request, route=name, limits=limits)


def execute(case, route):
    definitions = members(case, route)
    proofs, results, works = [], [], []
    for request, backend in definitions:
        proof, result, work = produce(case['source'], request, case['limits'], backend)
        proofs.append(proof)
        results.append(result)
        works.append(work)
    certificate = dict(schema=ENVELOPE, delivery=delivery(case, route),
                       request_sha256=digest(case['request']), packets=proofs)
    result = dict(status=aggregate(results), members=results)
    return certificate, result, dict(members=works)


def run(case, route, audit=False, memory=False):
    from .trace import Trace
    require(not (audit and memory), 'separate call audit and memory')
    trace = Trace() if audit else None
    if memory:
        tracemalloc.start()
    started = time.perf_counter_ns()
    with trace if trace is not None else nullcontext():
        proof, result, work = execute(case, route)
        # Delivery encoding is charged, not silently moved out of build time.
        wire = canonical(proof)
        canonical(result)
    elapsed = time.perf_counter_ns() - started
    peak = tracemalloc.get_traced_memory()[1] if memory else None
    if memory:
        tracemalloc.stop()
    saved = dict(certificate=proof, result=result, work=work)
    out = dict(identity=identity(saved), build_ns=elapsed, certificate_bytes=len(wire.encode()),
               native_packet_bytes=sum(len(canonical(p).encode()) for p in proof['packets'] if p is not None),
               source_bytes=len(case['source'].encode()), request_bytes=len(canonical(case['request']).encode()),
               followup_bytes=len(canonical(case['followups']).encode()), traced_peak_bytes=peak,
               delivery=delivery(case, route), member_count=len(proof['packets']))
    if audit:
        out.update(saved, trace=trace.report(), diagnostic_bytes=len(canonical(work).encode()))
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', type=Path)
    parser.add_argument('route')
    parser.add_argument('output', type=Path)
    parser.add_argument('--audit', action='store_true')
    parser.add_argument('--memory', action='store_true')
    args = parser.parse_args()
    save_json(args.output, run(load_json(args.case), args.route, args.audit, args.memory))
