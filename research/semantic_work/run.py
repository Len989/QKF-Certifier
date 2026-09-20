"""Retained PR38 control, not the future demand-driven producer. No hidden fallback."""
from .contract import PROOF, canonical, digest, need, request, snapshot
from .evidence import concrete_witness, refutation, unresolved


def _outcome(r, route, result):
    return {'schema': 'qkf-semantic-outcome-v1', 'request_sha256': digest(r),
        'status': result['status'], 'route': route, 'requested_guarantee': r['guarantee'],
        'achieved': {'target_checked': result.get('target_checked', False),
                     'all_positive_widths': result.get('all_positive_widths', False),
                     'source_interface': 'exact_and_minimal_finite_model' if route == 'covered-v6'
                       and result.get('target_checked') else None},
        'legacy_result': snapshot(result), 'new_forcing_or_visibility_claim': False}


def check(raw_request, raw_proof):
    """Semantic replay only. No meter, search, cached outcome or recorded cost is trusted."""
    r, p = request(raw_request), snapshot(raw_proof)
    need(not r['conditions'], 'unsupported conditional proof')
    need(type(p) is dict and set(p) == {'schema', 'request_sha256', 'route', 'legacy', 'result'}
         and p['schema'] == PROOF and p['request_sha256'] == digest(r), 'proof/request binding')
    if p['route'] == 'covered-v6':
        from research.signed_context.session import check as old_check
        result = old_check(r['source'], r['consumer']['target'], p['legacy'])
    elif p['route'] == 'concrete-v1':
        result = refutation(concrete_witness(r, p['legacy']))
    else:
        raise ValueError('unsupported proof route')
    fresh = _outcome(r, p['route'], result)
    need(canonical(p['result']) == canonical(fresh), 'saved result is not evidence')
    return fresh


def _wrap(r, route, legacy, result):
    p = {'schema': PROOF, 'request_sha256': digest(r), 'route': route,
         'legacy': legacy, 'result': _outcome(r, route, result)}
    # Retained producer already verifies its output; do not inflate baseline work
    # by an artificial second replay. External check() re-establishes it afresh.
    return p['result'], p


def execute(r, meter):
    """Execute within ONE caller-owned meter; no counter resets between attempts."""
    if r['conditions']:
        return unresolved('unsupported_conditions', {'conditions': r['conditions']}).data(), None
    if r['strategy'] == 'witness_then_covered':
        with meter.stage('concrete_precheck', attempt=True) as stage:
            from research.signed_witness.producer import probe
            legacy, result, search = probe(r['source'], r['consumer']['target'], limits=r['search'])
            stage['outcome'] = result['status']
            stage['search'] = search
        if legacy is not None:
            with meter.stage('packaging'):
                return _wrap(r, 'concrete-v1', legacy, result)
        if result['status'] == 'unsupported':
            return unresolved('unsupported', result).data(), None
        with meter.stage('fallback_decision'):
            meter.note_fallback()
    with meter.stage('covered_control', attempt=True) as stage:
        from research.unified.v6 import prove
        result, legacy = prove(r['source'], r['consumer']['target'], budgets=r['budget']['backend'])
        stage['outcome'] = result['status']
    if legacy is None:
        return _outcome(r, 'covered-v6', result), None
    with meter.stage('packaging'):
        return _wrap(r, 'covered-v6', legacy, result)


def run(raw_request, *, forbid_full=False):
    """Diagnostic report plus independently checkable proof. Resource aborts issue no proof."""
    from .meter import Meter, StopWork, ForbiddenWork
    # Validation and route imports are INSIDE time/memory/call accounting. The
    # request's work limit is enforced immediately after validating that limit.
    meter = Meter(max_work=20_000_000, forbid_full=forbid_full)
    result, proof = None, None
    with meter:
        try:
            with meter.stage('request_validation'):
                r = request(raw_request)
                meter.max_work = r['budget']['max_work']
                meter.max_attempts = r['budget']['max_attempts']
                if meter.counts['work_calls'] > meter.max_work:
                    raise StopWork('global budget consumed during request validation')
            result, proof = execute(r, meter)
            with meter.stage('serialization'):
                proof_bytes = 0 if proof is None else len(canonical(proof).encode())
        except StopWork as exc:
            result, proof = unresolved('budget_exhausted', {'reason': str(exc)}).data(), None
            proof_bytes = 0
        except ForbiddenWork:
            raise  # A violated construction prohibition is a failed test, not a solver outcome.
    return {'schema': 'qkf-semantic-run-v1', 'result': result, 'proof': proof,
            'certificate_bytes': proof_bytes, 'work': meter.report}
