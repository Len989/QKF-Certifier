"""Experimental PR49 builder; unchanged public schema and independent checker."""
import hashlib
import time
from research.applicable_summary.contract import (
    request, interface, SIGNED, PACKET, RESULT, Unsupported, require, canonical)
from research.source_lemmas.context import source_text
from research.prepared_context.values import plain
from research.signed_compact import dag
from .export import Emission


def build(source, raw_request, *, backend='query', policy='no_lemmas', limits=None):
    started = time.perf_counter_ns()
    phases, work_backend, extraction = {}, {}, {}
    packet = None
    try:
        source = source_text(source)
        r = request(raw_request)
        begin = time.perf_counter_ns()
        if r['profile'] != SIGNED:
            raise Unsupported('direct emission supports the signed profile')
        from .producer import prove
        produced, result, work_backend = prove(source, r['query'], backend=backend, policy=policy, limits=limits)
        phases['backend_ns'] = time.perf_counter_ns() - begin
        if produced is None:
            require(result['status'] in ('unsupported', 'budget_exhausted'), 'missing producer certificate')
            result = dict(schema=RESULT, profile=r['profile'], applicable=False, goals=[],
                status='unsupported' if result['status'] == 'unsupported' else 'unresolved',
                reason=result.get('reason', 'resource_budget') if result['status'] == 'unsupported' else 'resource_budget',
                backend_result=result)
        else:
            begin = time.perf_counter_ns()
            from research.applicable_summary.audit import ExecutionGuard
            from research.applicable_summary.checker import check, package
            with ExecutionGuard(checking=True, witness=any(g['status'] == 'refuted' for g in result['goals'])):
                if type(produced) is Emission:
                    # Only private checked conclusions propose this interface.
                    # The serialized result below is the public trust boundary.
                    packet = dag.pack(dict(schema=PACKET, request=r,
                        source_sha256=hashlib.sha256(source.encode()).hexdigest(), kind='native_direct',
                        evidence=plain(produced.evidence), interface=interface(r, result['goals'])))
                    checked = check(source, r, packet)
                    verified = checked.result()
                    require([g['status'] for g in verified['goals']] == [g['status'] for g in result['goals']],
                            'final serialized goal outcomes differ')
                    result = verified
                    extraction = dict(work_backend['emission'], final_envelopes=1, public_cold_checks=1)
                else:
                    from research.applicable_summary.export import extract
                    kind, evidence, extraction = extract(source, r['query'], produced)
                    require(kind == 'native_batch', 'fallback must retain scoped lower models')
                    packet, result = package(source, r, kind, evidence)
                    extraction.update(work_backend['emission'], final_envelopes=1, public_cold_checks=1,
                                      fallback_replays='native check, extract load, components, final public check')
                phases['pack_and_cold_check_ns'] = time.perf_counter_ns() - begin
    except Unsupported as exc:
        result = dict(schema=RESULT, status='unsupported', reason=str(exc), goals=[], applicable=False)
    work = dict(schema='qkf-summary-work-v1', elapsed_ns=time.perf_counter_ns() - started,
                phases=phases, backend=work_backend, extraction=extraction,
                packet_bytes=0 if packet is None else len(canonical(packet).encode()),
                scope='all admission/search/checkpoint/emission work, fallback when needed, final encoding and independent public check; excludes CLI I/O; not a speedup benchmark')
    return packet, result, work
