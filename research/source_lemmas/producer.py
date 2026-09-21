"""Shared native questions, checked ground lemmas, and independent consumers."""
from research.wordexpr.frontend import Unsupported
from research.ground_query.schema import parse
from research.source_planner.language import State
from research.source_planner.native import derive
from research.signed_compact import dag
from .audit import Audit, BudgetStop
from .context import options, target_context, scope, digest, canonical, snapshot, require
from .checker import open_context, check
from .terms import native_entry, roots


def active_basis(presentation, cut):
    natives, lemmas = presentation.native(), presentation.lemmas()
    omitted = set(lemmas[0]['basis']['native']) if cut and lemmas else set()
    return dict(native=[r['id'] for r in natives if r['id'] not in omitted],
                lemmas=[])


def eligible(checked, presentation):
    """Eligibility reads a checked chronological proof, never an expected answer."""
    from .context import thaw
    item = thaw(checked._item)
    if item['kind'] != 'ground' or checked.result()['status'] != 'certified':
        return False
    claim = roots(target_context(presentation.context(), thaw(checked._request)))
    premises = presentation.premises(item['basis'], item['epoch'])
    if claim[0] == claim[1] or claim in premises or claim[::-1] in premises:
        return False
    proof = item['certificate']
    pending, seen, axioms, congruences = list(proof['goals'][0]['path']), set(), set(), 0
    while pending:
        i = pending.pop()
        if i in seen:
            continue
        seen.add(i)
        event = proof['events'][i]
        if event['rule'] == 'axiom':
            axioms.add(event['equation'])
        else:
            congruences += 1
            pending.extend(p for path in event['premises'] for p in path)
    return len(axioms) >= 2 and congruences > 0


def checkpoint(presentation, ctx, state, audit, route, basis):
    with audit.stage('build_current_ground_obligation'):
        epoch = presentation.epoch()
        lemmas = presentation.lemmas()
        via = lemmas[0]['id'] if lemmas else None
        claim = presentation.residual_claim(roots(ctx), via, epoch)
        request = presentation.request(claim, basis, epoch)
        inp = parse(request)
        endpoint = max(inp.depths[x] for p in inp.queries for x in p)
        cap = min(inp.horizon, audit.options['max_horizon'])

    def probe(horizon):
        audit.checkpoint()
        if horizon < endpoint:
            item = dict(kind='inactive', epoch=epoch, basis=basis, via_lemma=via, horizon=horizon)
            stats, backend = {}, 'inactive_query'
        else:
            with audit.stage('ground_search'):
                if route == 'direct_cache' and horizon == inp.horizon:
                    from research.source_query.ordinary import prove
                    core, stats = prove(request)
                    backend = 'ordinary_full_CC'
                else:
                    from research.ground_query.producer import prove
                    core, stats = prove(request, mode='entailment', horizon=horizon)
                    backend = 'Paper_II_query_subterms'
            item = dict(kind='ground', epoch=epoch, basis=basis, via_lemma=via, certificate=core)
            audit.counts['ground_searches'] += 1
            audit.counts['ground_proof_events'] += len(core['events'])
            audit.counts['ground_congruence_events'] += sum(e['rule'] == 'congruence' for e in core['events'])
        with audit.stage('independent_obligation_check'):
            checked = presentation.verify(ctx.request, item)
        result = checked.result()
        identity = digest(dict(scope=scope(ctx), request=ctx.request, item=item))
        audit.checkpoints.append(dict(id=identity, request=ctx.request, item=item,
                                      result=result, backend=backend, search=stats))
        audit.counts['ground_checkpoints'] += 1
        audit.counts['checkpoint_proof_bytes'] += len(canonical(item).encode())
        if via is not None or basis['lemmas']:
            audit.counts['lemma_backed_checkpoints'] += 1
        state.live_checkpoint = state.live_model = None
        if item['kind'] == 'ground' and result['status'] == 'unresolved':
            state.live_checkpoint = identity
            state.live_model = core['models'][core['goals'][0]['model']]
        audit.decisions.append(dict(event='checked_obligation', id=identity, epoch=epoch,
                                    status=result['status'], horizon=horizon, basis=basis))
        return item, checked

    initial = cap if route == 'direct_cache' else min(endpoint, cap)
    item, checked = probe(initial)
    if checked.result()['reason'] == 'insufficient_horizon' and endpoint <= initial < cap:
        audit.decisions.append(dict(event='grow_horizon', previous=initial, horizon=cap,
                                    invalidated_separator=state.live_checkpoint))
        state.live_checkpoint = state.live_model = None
        item, checked = probe(cap)
    return item, checked


def prove(source, batch, *, route='no_lemmas', limits=None):
    require(route in ('reuse', 'direct_cache', 'no_lemmas'), 'lemma route')
    audit = Audit(options(limits))
    presentation, state, packet, result = None, None, None, None
    items, outcomes, cache, diagnoses = [], [], {}, []
    seen_goals = set()
    with audit:
        try:
            with audit.stage('source_and_independent_goals_admission'):
                presentation, requests = open_context(source, batch)
                anchor = presentation.context()
            if anchor.domain:
                state = State(anchor, audit)
            for index, request in enumerate(requests):
                audit.closed = False
                key = canonical(request)
                if key in cache:
                    previous = cache[key]
                    items.append(dict(kind='cached_goal', previous=previous))
                    outcomes.append(snapshot(outcomes[previous]))
                    diagnoses.append(dict(stop='exact_checked_goal_cache', previous=previous))
                    audit.counts['exact_goal_cache_hits'] += 1
                    audit.decisions.append(dict(event='cached_goal', goal=index, previous=previous))
                    audit.closed = True
                    continue
                audit.counts['uncached_goal_checks'] += 1
                if key not in seen_goals:
                    seen_goals.add(key)
                    audit.counts['distinct_goals'] += 1
                ctx = target_context(anchor, request)
                if not ctx.domain:
                    item = dict(kind='empty')
                    checked = presentation.verify(request, item)
                    diagnosis = dict(stop='empty_guard')
                else:
                    state.ctx = ctx
                    state.roots = state.graph.source(), state.graph.target(ctx.spec['target'])
                    state.live_checkpoint = state.live_model = None
                    cut = route != 'no_lemmas' and bool(presentation.lemmas())
                    basis = active_basis(presentation, cut)
                    item, checked = checkpoint(presentation, ctx, state, audit, route, basis)
                    diagnosis = None
                    while checked.result()['reason'] == 'not_entailed_from_current_presentation':
                        with audit.stage('candidate_selection_and_pullback'):
                            selected = state.next_question()
                        if selected is None:
                            if cut and basis != active_basis(presentation, False):
                                audit.decisions.append(dict(event='reopen_native_basis', goal=index,
                                    invalidated_separator=state.live_checkpoint))
                                audit.counts['native_basis_reopenings'] += 1
                                state.live_checkpoint = state.live_model = None
                                cut = False
                                basis = active_basis(presentation, cut)
                                item, checked = checkpoint(presentation, ctx, state, audit, route, basis)
                                continue
                            break
                        question, origin = selected
                        audit.origin = dict(origin, goal=index)
                        state.tried.add(digest(question))
                        with audit.stage('selected_native_question'):
                            value = audit.fact(question, lambda: derive(ctx, state.graph, question))
                            changed = state.add(value)
                        audit.origin = None
                        if changed:
                            with audit.stage('check_new_native_foundation'):
                                fact, endpoints = value
                                presentation = presentation.add_native(native_entry(ctx, state.graph, fact, endpoints))
                            # No old model is promoted to a residual after this extension.
                            item = checked = None
                            basis = active_basis(presentation, cut)
                            item, checked = checkpoint(presentation, ctx, state, audit, route, basis)
                    if checked.result()['reason'] == 'not_entailed_from_current_presentation':
                        diagnosis = dict(ground='not_entailed_from_current_presentation',
                            source='additional_source_facts_required', representation='candidate_policy_exhausted',
                            claim='diagnostic only; not global impossibility', fallback='disabled')
                        with audit.stage('bounded_guarded_witness'):
                            from research.source_query.producer import bounded_witness
                            negative = bounded_witness(ctx, audit.options, audit)
                        if negative is not None:
                            item = dict(kind='witness', certificate=negative)
                            with audit.stage('independent_concrete_witness_check'):
                                checked = presentation.verify(request, item)
                            diagnosis['source'] = 'concrete_violation'
                    if checked.result()['status'] == 'certified' and route != 'no_lemmas' and not presentation.lemmas():
                        with audit.stage('checked_lemma_eligibility_and_promotion'):
                            audit.counts['lemma_eligibility_attempts'] += 1
                            if audit.options['max_lemmas'] and eligible(checked, presentation):
                                presentation, lemma = presentation.promote(checked)
                                audit.counts['lemma_promotions'] += 1
                                audit.decisions.append(dict(event='promote_checked_lemma', goal=index,
                                    lemma=lemma['id'], basis=lemma['basis'], epoch=presentation.epoch()))
                                item = dict(kind='lemma', lemma=lemma['id'])
                                checked = presentation.verify(request, item)
                            else:
                                audit.counts['declined_lemma_candidates'] += 1
                    if item['kind'] == 'ground' and checked.result()['status'] == 'certified' and item['via_lemma'] is not None:
                        audit.counts['later_goals_using_lemma'] += 1
                current = checked.result()
                audit.closed = True
                # A finite lower model is tied to its current E/E+. It is not
                # an immutable source verdict and cannot be a cross-goal cache hit.
                if current['status'] in ('certified', 'refuted', 'verified_empty_domain'):
                    cache[key] = index
                items.append(item)
                outcomes.append(current)
                diagnoses.append(diagnosis or dict(stop=current['reason']))
                audit.decisions.append(dict(event='stop_goal', goal=index, status=current['status'], reason=current['reason']))
            with audit.stage('portable_DAG_pack'):
                payload = presentation.payload(items)
                packet = dag.pack(payload)
                audit.counts['expanded_proof_bytes'] = len(canonical(payload).encode())
                audit.counts['packet_bytes'] = len(canonical(packet).encode())
            with audit.stage('builtin_cold_package_check'):
                replayed = check(source, batch, packet)
                require(replayed == outcomes, 'cold checked packet differs from producer results')
            result = dict(status='completed', goals=outcomes)
        except Unsupported as exc:
            packet, result = None, dict(status='unsupported', reason=str(exc), goals=[])
        except BudgetStop as exc:
            packet, result = None, dict(status='budget_exhausted', reason=str(exc), goals=[])
    work = audit.report()
    work.update(route=route, candidate_language='PR43 questions plus first checked nontrivial goal lemma',
        diagnoses=diagnoses, completed_goals_before_stop=len(outcomes),
        foundations=None if presentation is None else
            dict(scope=scope(presentation.context()), E=presentation.native(), E_plus=presentation.lemmas()),
        certificate_bytes=0 if packet is None else len(canonical(packet).encode()),
        term_dag=[] if state is None else state.graph.nodes,
        cross_goal_lemma_reuse=route != 'no_lemmas')
    return packet, result, work
