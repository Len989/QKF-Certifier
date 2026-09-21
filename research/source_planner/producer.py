"""Select one source question at a time and stop on checked sufficiency."""
from research.wordexpr.frontend import Unsupported
from research.ground_query.schema import parse
from .audit import Audit, BudgetStop
from .context import prepare, options as validate_options, envelope, digest, canonical, require
from .checker import check
from .language import State


def checkpoint(source, ctx, state, audit, route, fixed=None):
    with audit.stage('export_current_E_and_consumer'):
        ground, facts = state.export() if fixed is None else fixed
        inp = parse(ground)
        endpoint = max(inp.depths[x] for pair in inp.queries for x in pair)
        cap = min(inp.horizon, audit.options['max_horizon'])

    def probe(horizon):
        audit.checkpoint()
        if horizon < endpoint:
            cert = envelope(ctx, 'inactive', dict(request=ground, facts=facts, horizon=horizon))
            stats, backend = {}, 'inactive_query'
        else:
            with audit.stage('ground_search'):
                if route == 'ordinary' and horizon == inp.horizon:
                    from research.source_query.ordinary import prove
                    core, stats = prove(ground)
                    backend = 'ordinary_full_CC'
                else:
                    from research.ground_query.producer import prove
                    core, stats = prove(ground, mode='entailment', horizon=horizon)
                    backend = 'Paper_II_query_subterms'
                cert = envelope(ctx, 'ground', dict(request=ground, facts=facts, certificate=core))
        with audit.stage('independent_checkpoint_check'):
            result = check(source, ctx.request, cert)
        identity = digest(cert)
        audit.checkpoints.append(dict(id=identity, E_version=state.version,
                                      certificate=cert, result=result, backend=backend, search=stats))
        audit.counts['ground_checkpoints'] += 1
        audit.counts['checkpoint_proof_bytes'] += len(canonical(cert).encode())
        audit.decisions.append(dict(event='checked_obligation', id=identity, E_version=state.version,
                                    horizon=horizon, final_horizon=inp.horizon,
                                    relation=result.get('ground_relation'), status=result['status']))
        state.live_checkpoint = None
        state.live_model = None
        if cert['kind'] == 'ground' and result['status'] == 'unresolved':
            goal = core['goals'][0]
            state.live_checkpoint = identity
            state.live_model = core['models'][goal['model']]
        return cert, result

    initial = cap if route == 'ordinary' else min(endpoint, cap)
    cert, result = probe(initial)
    if result['reason'] == 'insufficient_horizon' and endpoint <= initial < cap:
        audit.decisions.append(dict(event='grow_horizon', E_version=state.version,
                                    previous=initial, horizon=cap, retired_lower_model=state.live_checkpoint))
        state.live_model = state.live_checkpoint = None
        cert, result = probe(cap)
    return cert, result


def prove(source, request, *, route='planner', limits=None, fallback=False):
    require(route in ('planner', 'ordinary', 'eager') and type(fallback) is bool, 'planner route/fallback')
    opts = validate_options(limits)
    audit = Audit(opts)
    cert, result, ctx, state = None, None, None, None
    with audit:
        try:
            with audit.stage('source_admission'):
                ctx = prepare(source, request)
            if not ctx.domain:
                from research.source_query.checker import envelope as previous_envelope
                cert = envelope(ctx, 'legacy', dict(proof=previous_envelope(ctx, 'empty', {})))
                with audit.stage('independent_consumer_check'):
                    result = check(source, request, cert)
            else:
                with audit.stage('consumer_and_source_IR'):
                    state = State(ctx, audit)
                    audit.counts['compiled_word_nodes'] = len(ctx.ir['nodes'])
                    audit.counts['compiled_source_atoms'] = len(ctx.ir['atoms'])
                fixed = None
                if route == 'eager':
                    with audit.stage('PR41_eager_native_collection'):
                        from research.source_query.facts import collect
                        fixed = collect(ctx, audit)
                        state.version = len(fixed[1])
                cert, result = checkpoint(source, ctx, state, audit, route, fixed)
                while route != 'eager' and result['reason'] == 'not_entailed_from_current_E':
                    with audit.stage('candidate_selection_and_pullback'):
                        selected = state.next_question()
                    if selected is None:
                        break
                    question, origin = selected
                    audit.origin = origin
                    state.tried.add(digest(question))
                    audit.decisions.append(dict(event='source_fact_gap', E_version=state.version,
                                                separator=state.live_checkpoint, selected=question))
                    with audit.stage('selected_native_question'):
                        from .native import derive
                        value = audit.fact(question, lambda: derive(ctx, state.graph, question))
                        changed = state.add(value)
                    audit.origin = None
                    if changed:
                        # Any previous negative model belongs to the old E.
                        # Do not publish it as the residual of this new E if
                        # a later search/check exhausts its budget.
                        cert, result = None, None
                        cert, result = checkpoint(source, ctx, state, audit, route)
                if result['reason'] == 'not_entailed_from_current_E':
                    audit.diagnosis = dict(stage='native_search', ground='not_entailed_from_current_E',
                        source='additional_source_facts_required', representation='candidate_language_exhausted',
                        claim='bounded policy exhausted; not global semantic impossibility')
                    audit.decisions.append(dict(event='candidate_language_exhausted', E_version=state.version,
                                                current_obligation=state.live_checkpoint))
                    with audit.stage('bounded_guarded_witness'):
                        from research.source_query.producer import bounded_witness
                        negative = bounded_witness(ctx, opts, audit)
                    if negative is not None:
                        cert = envelope(ctx, 'legacy', dict(proof=negative))
                        with audit.stage('independent_counterexample_check'):
                            result = check(source, request, cert)
                        audit.diagnosis['source'] = 'concrete_violation'
                    elif fallback:
                        audit.counts['fallback_attempts'] += 1
                        audit.allow_builders = True
                        audit.decisions.append(dict(event='explicit_fallback', prior_obligation=state.live_checkpoint,
                                                    prior_fact_attempts=len(audit.attempts)))
                        try:
                            with audit.stage('covered_guarded_fallback'):
                                from research.source_query.fallback import discover
                                previous, fallback_result = discover(source, ctx, opts, audit)
                        finally:
                            audit.allow_builders = False
                        cert = None if previous is None else envelope(ctx, 'legacy', dict(proof=previous))
                        if cert is None:
                            result = dict(status='budget_exhausted', reason='explicit_fallback_budget', detail=fallback_result)
                        else:
                            with audit.stage('independent_fallback_check'):
                                result = check(source, request, cert)
                        audit.diagnosis['fallback'] = result.get('reason', result['status'])
                    else:
                        audit.diagnosis['witness'] = 'no_counterexample_found_within_registered_bounds'
                        audit.diagnosis['fallback'] = 'disabled'
            if result['status'] in ('certified', 'verified_empty_domain', 'refuted'):
                audit.closed = True
            if audit.diagnosis is None:
                audit.diagnosis = dict(stop=result.get('reason', result['status']))
            audit.decisions.append(dict(event='stop', status=result['status'], reason=result.get('reason')))
        except Unsupported as exc:
            cert, result = None, dict(status='unsupported', reason=str(exc), target_checked=False)
            audit.diagnosis = dict(stop='unsupported_source_or_contract')
        except BudgetStop as exc:
            cert, result = None, dict(status='budget_exhausted', reason=str(exc), target_checked=False)
            audit.diagnosis = dict(stop='resource_budget', detail=str(exc))
    report = audit.report()
    report.update(route=route, source_binding=None if ctx is None else ctx.binding(),
                  automatic_observation_planner=route != 'eager',
                  certificate_bytes=0 if cert is None else len(canonical(cert).encode()),
                  term_dag=[] if state is None or route == 'eager' else state.graph.nodes,
                  E_version=0 if state is None else state.version,
                  cross_goal_lemma_reuse=False)
    return cert, result, report
