"""Research builder. Expensive mechanisms stay explicit after A1/A2."""
import hashlib
import time
from .contract import request, SIGNED, PHASE, RESULT, Unsupported, require, canonical


def build(source, raw_request, *, route=None, limits=None):
    started = time.perf_counter_ns()
    phases, backend, extraction = {}, {}, {}
    packet = None
    try:
        r = request(raw_request)
        begin = time.perf_counter_ns()
        if r['profile'] == SIGNED:
            from research.source_lemmas.producer import prove
            cert, result, backend = prove(source, r['query'], route='no_lemmas' if route is None else route, limits=limits)
        else:
            from research.source_forcing.producer import prove
            cert, result, backend = prove(source, r['query'], route='direct_cell' if route is None else route, limits=limits)
        phases['backend_ns'] = time.perf_counter_ns() - begin
        if cert is None:
            require(result['status'] in ('unsupported', 'budget_exhausted'), 'missing producer certificate')
            result = dict(schema=RESULT, profile=r['profile'], applicable=False, goals=[],
                status='unsupported' if result['status'] == 'unsupported' else 'unresolved',
                reason=result.get('reason', 'resource_budget') if result['status'] == 'unsupported' else 'resource_budget',
                backend_result=result)
        else:
            begin = time.perf_counter_ns()
            from .audit import ExecutionGuard
            with ExecutionGuard(checking=True, witness=any(g['status'] == 'refuted' for g in result.get('goals', []))):
                if r['profile'] == SIGNED:
                    from .export import extract
                    kind, evidence, extraction = extract(source, r['query'], cert)
                else:
                    kind, evidence = 'phase_cell', cert
                phases['dependency_export_ns'] = time.perf_counter_ns() - begin
                begin = time.perf_counter_ns()
                from .checker import package
                packet, result = package(source, r, kind, evidence)
                phases['pack_and_cold_check_ns'] = time.perf_counter_ns() - begin
    except Unsupported as exc:
        result = dict(schema=RESULT, status='unsupported', reason=str(exc), goals=[], applicable=False)
    work = dict(schema='qkf-summary-work-v1', elapsed_ns=time.perf_counter_ns() - started,
                phases=phases, backend=backend, extraction=extraction,
                packet_bytes=0 if packet is None else len(canonical(packet).encode()),
                scope='backend preparation/search/checks, dependency extraction and builtin envelope checks; excludes CLI I/O; not a speedup benchmark')
    return packet, result, work


def refine(source, summary, new_request, *, route=None, limits=None):
    """Explicit new build; no claim of incremental search or transported scope."""
    from .runtime import CheckedSummary
    require(type(summary) is CheckedSummary, 'refinement requires a checked summary')
    require(type(source) is str and hashlib.sha256(source.encode()).hexdigest() == summary.result()['source_sha256'],
            'changed source requires a separate build and fresh foundations')
    return build(source, new_request, route=route, limits=limits)
