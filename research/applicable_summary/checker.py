"""Independent envelope checker and compilation of a sufficient finite action."""
import hashlib
from research.signed_compact import dag
from research.signed_context.io import source_text
from .contract import (PACKET, RESULT, SIGNED, PHASE, request, canonical, snapshot,
                       interface, status, fields, require)


def replay(source, r, kind, evidence):
    if r['profile'] == SIGNED:
        q = r['query']
        if kind == 'native_direct':
            from .direct import check
            return check(source, q, evidence)
        if kind == 'native_batch':
            from research.source_lemmas.checker import check
            results = check(source, q, dag.pack(evidence))
            explanations = [dict(kind='retained_native_presentation', goal=i,
                item=evidence['items'][i], foundations=dict(scope=evidence['scope'],
                    E=evidence['E'], E_plus=evidence['E_plus'])) for i in range(len(results))]
            return results, explanations
        require(kind in ('source_query', 'source_plan') and len(q['requests']) == 1,
                'single-consumer PR41/43 adapter')
        if kind == 'source_query':
            from research.source_query.checker import check
        else:
            from research.source_planner.checker import check
        result = check(source, q['requests'][0], evidence)
        return [result], [dict(kind='retained_' + kind, certificate=evidence)]
    require(r['profile'] == PHASE and kind == 'phase_cell', 'profile/certificate mismatch')
    from research.source_forcing.checker import check
    result = check(source, r['query'], evidence)
    return result['goals'], [dict(kind='local_phase', goal=i, label=r['query']['label'],
        route=evidence['kind'], preparation=evidence['preparation'], evidence=evidence['evidence'])
        for i in range(len(result['goals']))]


def components(source, raw_request, kind, evidence):
    source = source_text(source)
    r = request(raw_request)
    results, explanations = replay(source, r, kind, snapshot(evidence))
    action = interface(r, results)
    applicable = (action['values'] is not None if r['profile'] == SIGNED else bool(action['cells']))
    outcome = dict(schema=RESULT, profile=r['profile'], status=status(results), goals=results,
                   applicable=applicable, lean_checked=False,
                   guarantee='conditional_boolean_consumer' if r['profile'] == SIGNED else 'one_local_phase_cell',
                   source_sha256=hashlib.sha256(source.encode()).hexdigest())
    return r, action, outcome, explanations


def check(source, raw_request, packet):
    """Check all foundations; only this path issues an applicable capability."""
    data = dag.unpack(packet)
    fields(data, ('schema', 'request', 'source_sha256', 'kind', 'evidence', 'interface'), 'summary envelope')
    require(data['schema'] == PACKET, 'summary envelope version')
    r = request(raw_request)
    require(canonical(r) == canonical(data['request']), 'independent consumer/request binding')
    require(type(data['kind']) is str, 'certificate family')
    r, action, result, explanations = components(source, r, data['kind'], data['evidence'])
    require(data['source_sha256'] == result['source_sha256'], 'exact source identity')
    require(canonical(data['interface']) == canonical(action), 'execution form differs from proved action')
    from .runtime import _issue
    return _issue(r, action, result, explanations, packet)


def from_certificate(source, raw_request, certificate, *, kind):
    """Explicit import of a native PR41/42/43/44 certificate, with full replay."""
    require(kind in ('source_query', 'source_plan', 'native_batch', 'phase_cell'), 'import certificate kind')
    evidence = dag.unpack(certificate) if kind == 'native_batch' else snapshot(certificate)
    return package(source, raw_request, kind, evidence)


def package(source, raw_request, kind, evidence):
    r, action, result, _ = components(source, raw_request, kind, evidence)
    packet = dag.pack(dict(schema=PACKET, request=r, source_sha256=result['source_sha256'],
                           kind=kind, evidence=evidence, interface=action))
    # The serialized execution form passes the same boundary as a cold consumer.
    checked = check(source, r, packet)
    return packet, checked.result()
