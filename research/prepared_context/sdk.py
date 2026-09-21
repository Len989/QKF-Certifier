"""PR48 signed builder with the unchanged PR45 export/package/cold-check path."""
import time
from research.applicable_summary.contract import request, SIGNED, RESULT, Unsupported, require, canonical


def build(source, raw_request, *, backend='query', policy='no_lemmas', limits=None):
    started = time.perf_counter_ns()
    phases, work_backend, extraction = {}, {}, {}
    packet = None
    try:
        r = request(raw_request)
        begin = time.perf_counter_ns()
        if r['profile'] == SIGNED:
            from .producer import prove
            cert, result, work_backend = prove(source, r['query'], backend=backend, policy=policy, limits=limits)
        else:
            raise Unsupported('prepared context supports the signed profile')
        phases['backend_ns'] = time.perf_counter_ns() - begin
        if cert is None:
            require(result['status'] in ('unsupported', 'budget_exhausted'), 'missing producer certificate')
            result = dict(schema=RESULT, profile=r['profile'], applicable=False, goals=[],
                status='unsupported' if result['status'] == 'unsupported' else 'unresolved',
                reason=result.get('reason', 'resource_budget') if result['status'] == 'unsupported' else 'resource_budget',
                backend_result=result)
        else:
            begin = time.perf_counter_ns()
            from research.applicable_summary.audit import ExecutionGuard
            with ExecutionGuard(checking=True, witness=any(g['status'] == 'refuted' for g in result.get('goals', []))):
                from research.applicable_summary.export import extract
                kind, evidence, extraction = extract(source, r['query'], cert)
                phases['dependency_export_ns'] = time.perf_counter_ns() - begin
                begin = time.perf_counter_ns()
                from research.applicable_summary.checker import package
                packet, result = package(source, r, kind, evidence)
                phases['pack_and_cold_check_ns'] = time.perf_counter_ns() - begin
    except Unsupported as exc:
        result = dict(schema=RESULT, status='unsupported', reason=str(exc), goals=[], applicable=False)
    work = dict(schema='qkf-summary-work-v1', elapsed_ns=time.perf_counter_ns() - started,
                phases=phases, backend=work_backend, extraction=extraction,
                packet_bytes=0 if packet is None else len(canonical(packet).encode()),
                scope='backend preparation/search/checks, dependency extraction and builtin envelope checks; excludes CLI I/O; not a speedup benchmark')
    return packet, result, work
