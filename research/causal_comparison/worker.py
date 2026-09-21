"""One fresh build; no global semantic state shared between measured arms."""
import argparse
from contextlib import nullcontext
from pathlib import Path
import time
import tracemalloc
from .common import canonical, identity, load_json, save_json, require


def execute(case, route):
    require(route in case['routes'] and route not in case['unavailable'], 'unavailable route')
    source, request, limits = case['source'], case['request'], case['limits']
    if route.startswith(('sdk_', 'phase_')):
        from research.applicable_summary.producer import build
        actual = dict(sdk_default='no_lemmas', sdk_reuse='reuse', sdk_direct='direct_cache').get(route)
        if actual is None:
            actual = route[len('phase_'):]
        return build(source, request, route=actual, limits=limits)
    q = request['query']['requests'][0]
    require(len(request['query']['requests']) == 1, 'single-query baseline')
    if route == 'retained':
        require(not q['guards'] and q['width']['kind'] == 'all_positive', 'retained guarantee mismatch')
        from research.unified.v6 import prove
        result, proof = prove(source, q['target'], budgets=dict(
            max_states=limits['max_source_states'], max_target_states=limits['max_product_states']))
        return proof, result, dict(scope='unchanged v6 direct control; stronger covered source interface',
                                  limits=dict(max_states=limits['max_source_states'],
                                              max_target_states=limits['max_product_states']))
    if route in ('direct41', 'query41'):
        from research.source_query.producer import prove
        from research.source_query.audit import DEFAULTS
        return prove(source, q, route='ordinary' if route == 'direct41' else 'query',
                     limits={k: v for k, v in limits.items() if k in DEFAULTS})
    from research.source_planner.producer import prove
    from research.source_planner.context import DEFAULTS
    return prove(source, q, route='planner' if route == 'planner43' else 'eager',
                 limits={k: v for k, v in limits.items() if k in DEFAULTS})


def run(case, route, audit=False, memory=False):
    from .trace import Trace
    require(not (audit and memory), 'call trace and tracemalloc require separate children')
    trace = Trace() if audit else None
    if memory:
        tracemalloc.start()
    started = time.perf_counter_ns()
    with trace if trace is not None else nullcontext():
        proof, result, work = execute(case, route)
    elapsed = time.perf_counter_ns() - started
    peak = tracemalloc.get_traced_memory()[1] if memory else None
    if memory:
        tracemalloc.stop()
    saved = dict(certificate=proof, result=result, work=work)
    report = dict(identity=identity(saved), build_ns=elapsed,
                  certificate_bytes=0 if proof is None else len(canonical(proof).encode()),
                  source_bytes=len(case['source'].encode()), request_bytes=len(canonical(case['request']).encode()),
                  backend_phases=work.get('backend', work).get('phases', []),
                  backend_stages_ns=work.get('backend', work).get('stages_ns', {}),
                  SDK_phases=work.get('phases', {}) if 'backend' in work else {},
                  traced_peak_bytes=peak, extra_PR46_instrumentation=audit or memory)
    if audit:
        report.update(saved, trace=trace.report(), diagnostic_bytes=len(canonical(work).encode()))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', type=Path)
    parser.add_argument('route')
    parser.add_argument('output', type=Path)
    parser.add_argument('--audit', action='store_true')
    parser.add_argument('--memory', action='store_true')
    args = parser.parse_args()
    save_json(args.output, run(load_json(args.case), args.route, args.audit, args.memory))
