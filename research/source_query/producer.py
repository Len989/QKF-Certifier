"""Fixed native-fact preparation, two closure routes, then explicit fallback."""
from research.wordexpr.frontend import Unsupported
from research.signed_predicates.semantics import evaluate
from research.signed_predicates.frontend import target_value
from .context import prepare, require, digest, canonical
from .checker import check, envelope
from .audit import Audit, BudgetStop, limits as validate_limits


def bounded_witness(ctx, options, audit):
    widths = (range(1, options['max_witness_width'] + 1) if ctx.width is None else
              [ctx.width] if ctx.width <= options['max_witness_width'] else [])
    remaining = options['max_witness_evaluations']
    for width in widths:
        for raw in range(min(1 << width, remaining)):
            remaining -= 1
            audit.counts['witness_candidates'] += 1
            sign = raw >> (width - 1)
            if not ctx.guard(raw.bit_count(), sign):
                audit.counts['witness_guard_rejections'] += 1
                continue
            audit.counts['witness_source_evaluations'] += 1
            if evaluate(ctx.ir, raw, width) != target_value(ctx.spec['target'], raw.bit_count(), sign):
                return envelope(ctx, 'witness', {'width': width, 'input': raw})
        if remaining == 0:
            break
    return None


def prove(source, request, *, route='query', limits=None, fallback=False):
    require(route in ('query', 'ordinary') and type(fallback) is bool, 'explicit route/fallback')
    options = validate_limits(limits)
    audit = Audit(options)
    certificate, result, prior_ground = None, None, None
    ground_hash = None
    with audit:
        try:
            with audit.stage('admit_source_and_guard'):
                ctx = prepare(source, request)
                audit.counts['guard_domain_classes'] += len(ctx.domain)
            if not ctx.domain:
                certificate = envelope(ctx, 'empty', {})
            else:
                with audit.stage('native_fact_preparation'):
                    from .facts import collect
                    ground, facts = collect(ctx, audit)
                    ground_hash = digest(ground)
                with audit.stage('ground_' + route):
                    if route == 'query':
                        from research.ground_query.producer import prove as close
                        core, stats = close(ground, mode='entailment')
                    else:
                        from .ordinary import prove as close
                        core, stats = close(ground)
                    audit.closure = stats
                    certificate = envelope(ctx, 'ground', {'request': ground, 'facts': facts, 'certificate': core})
                with audit.stage('check_ground_consumer'):
                    result = check(source, request, certificate)
                if result['status'] == 'unresolved':
                    prior_ground = certificate
                    with audit.stage('bounded_guarded_witness'):
                        negative = bounded_witness(ctx, options, audit)
                    if negative is not None:
                        certificate, result = negative, None
                    elif fallback:
                        audit.counts['fallback_attempts'] += 1
                        audit.allow_builders = True
                        try:
                            with audit.stage('covered_guarded_fallback'):
                                from .fallback import discover
                                certificate, result = discover(source, ctx, options, audit)
                        finally:
                            audit.allow_builders = False
            if certificate is not None and result is None:
                with audit.stage('independent_consumer_check'):
                    result = check(source, request, certificate)
        except Unsupported as error:
            certificate = None
            result = {'status': 'unsupported', 'reason': str(error), 'target_checked': False}
        except BudgetStop as error:
            certificate = None
            result = {'status': 'budget_exhausted', 'reason': str(error), 'target_checked': False}
    report = audit.report()
    report.update(route=route, ground_request_sha256=ground_hash,
                  closure=getattr(audit, 'closure', None),
                  certificate_bytes=0 if certificate is None else len(canonical(certificate).encode()))
    if prior_ground is not None and (certificate is None or certificate['kind'] != 'ground'):
        report['prior_ground_evidence'] = prior_ground
    return certificate, result, report
