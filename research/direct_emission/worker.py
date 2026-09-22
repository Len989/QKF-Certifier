"""Fresh composition of unchanged producers and SDK adapters."""
import argparse
from contextlib import nullcontext
from pathlib import Path
import time
import tracemalloc
from .common import (canonical, digest, save_json, load_json, require, identity,
                     members, delivery, aggregate, ENVELOPE)


def produce(source, request, limits, route):
    if route.startswith('emitted_'):
        backend, policy = route[len('emitted_'):].split('_', 1)
        from .sdk import build
        return build(source, request, backend=backend, policy=policy, limits=limits)
    from research.prepared_context.worker import produce as previous
    return previous(source, request, limits, route)


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
