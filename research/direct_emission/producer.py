"""PR48 search and checked checkpoints, with incremental direct emission.

See ADAPTATION.json for the frozen source and the emission-only patch.
"""
from research.wordexpr.frontend import Unsupported
from research.source_planner.language import State
from research.source_planner.native import derive
from research.signed_compact import dag
from research.prepared_context.audit import Audit, BudgetStop
from research.source_lemmas.context import options, digest, canonical, snapshot, require
from research.prepared_context.values import plain
from research.source_lemmas.checker import check
from research.prepared_context.checker import open_context, native_entry
from .export import Assembler, Emission


def active_basis(presentation, cut):
    natives, lemmas = presentation._E, presentation._plus
    omitted = set(lemmas[0]['basis']['native']) if cut and lemmas else set()
    return dict(native=[r['id'] for r in natives if r['id'] not in omitted],
                lemmas=[])


def eligible(checked, presentation):
    """Eligibility reads a checked chronological proof, never an expected answer."""
    item = plain(checked._item)
    if item['kind'] != 'ground' or checked.result()['status'] != 'certified':
        return False
    claim = checked._ctx.claim
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


def checkpoint(presentation, ctx, state, audit, backend_choice, basis):
    with audit.stage('build_current_ground_obligation'):
        epoch = presentation.epoch()
        lemmas = presentation._plus
        via = lemmas[0]['id'] if lemmas else None
        prepared = presentation.prepare(ctx, basis, epoch, via)
        inp = prepared.ground
        endpoint = max(inp.depths[x] for p in inp.queries for x in p)
        cap = min(inp.horizon, audit.options['max_horizon'])

    def probe(horizon):
        audit.checkpoint()
        if horizon < endpoint:
            item = dict(kind='inactive', epoch=epoch, basis=basis, via_lemma=via, horizon=horizon)
            stats, backend = {}, 'inactive_query'
        else:
            with audit.stage('ground_search'):
                if backend_choice == 'ordinary':
                    from research.prepared_context.ordinary import prove
                    core, stats = prove(inp, horizon=horizon)
                    backend = 'ordinary_active_CC'
                else:
                    from research.prepared_context.query import prove
                    core, stats = prove(inp, mode='entailment', horizon=horizon)
                    backend = 'Paper_II_query_subterms'
            item = dict(kind='ground', epoch=epoch, basis=basis, via_lemma=via, certificate=core)
            audit.counts['ground_searches'] += 1
            audit.counts['ground_proof_events'] += len(core['events'])
            audit.counts['ground_congruence_events'] += sum(e['rule'] == 'congruence' for e in core['events'])
        with audit.stage('independent_obligation_check'):
            checked = presentation.verify(plain(ctx.request), item, prepared=prepared)
        result = checked.result()
        identity = digest(dict(scope=presentation.scope(), request=plain(ctx.request), item=item))
        audit.checkpoints.append(dict(id=identity, request=plain(ctx.request), item=item,
                                      result=result, backend=backend, search=stats))
        audit.counts['ground_checkpoints'] += 1
        audit.counts['checkpoint_proof_bytes'] += len(canonical(item).encode())
        if via is not None or basis['lemmas']:
            audit.counts['lemma_backed_checkpoints'] += 1
        state.live_checkpoint = state.live_model = None
        if item['kind'] == 'ground' and result['status'] == 'unresolved':
            state.live_checkpoint = identity
            state.live_model = presentation.model_for(prepared, checked)
        audit.decisions.append(dict(event='checked_obligation', id=identity, epoch=epoch,
                                    status=result['status'], horizon=horizon, basis=basis))
        return item, checked

    initial = cap if backend_choice == 'ordinary' else min(endpoint, cap)
    item, checked = probe(initial)
    if checked.result()['reason'] == 'insufficient_horizon' and endpoint <= initial < cap:
        audit.decisions.append(dict(event='grow_horizon', previous=initial, horizon=cap,
                                    invalidated_separator=state.live_checkpoint))
        state.live_checkpoint = state.live_model = None
        item, checked = probe(cap)
    return item, checked


def prove(source, batch, *, backend='query', policy='no_lemmas', limits=None):
    require(backend in ('ordinary', 'query'), 'ground backend')
    require(policy in ('no_lemmas', 'reuse'), 'lemma policy')
    audit = Audit(options(limits))
    presentation, state, packet, result = None, None, None, None
    assembler = None
    items, outcomes, cache, diagnoses = [], [], {}, []
    seen_goals = set()
    with audit:
        try:
            with audit.stage('source_and_independent_goals_admission'):
                presentation, requests = open_context(source, batch)
                anchor = presentation.context()
                assembler = Assembler(presentation)
            if anchor.domain:
                state = State(anchor, audit)
            for index, request in enumerate(requests):
                audit.closed = False
                key = canonical(request)
                if key in cache:
                    previous = cache[key]
                    items.append(dict(kind='cached_goal', previous=previous))
                    assembler.cached(previous)
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
                ctx = presentation.target(request)
                if not ctx.domain:
                    item = dict(kind='empty')
                    checked = presentation.verify(request, item)
                    diagnosis = dict(stop='empty_guard')
                else:
                    state.ctx = ctx
                    state.roots = state.graph.source(), state.graph.target(ctx.spec['target'])
                    state.live_checkpoint = state.live_model = None
                    cut = policy == 'reuse' and bool(presentation._plus)
                    basis = active_basis(presentation, cut)
                    item, checked = checkpoint(presentation, ctx, state, audit, backend, basis)
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
                                item, checked = checkpoint(presentation, ctx, state, audit, backend, basis)
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
                                presentation = presentation.add_native(native_entry(presentation, state.graph, fact, endpoints))
                                assembler.native(presentation)
                            # No old model is promoted to a residual after this extension.
                            item = checked = None
                            basis = active_basis(presentation, cut)
                            item, checked = checkpoint(presentation, ctx, state, audit, backend, basis)
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
                    if checked.result()['status'] == 'certified' and policy == 'reuse' and not presentation._plus:
                        with audit.stage('checked_lemma_eligibility_and_promotion'):
                            audit.counts['lemma_eligibility_attempts'] += 1
                            if audit.options['max_lemmas'] and eligible(checked, presentation):
                                presentation, lemma = presentation.promote(checked)
                                assembler.promote(checked, presentation)
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
                with audit.stage('emit_checked_goal'):
                    assembler.goal(checked)
                audit.closed = True
                # A finite lower model is tied to its current E/E+. It is not
                # an immutable source verdict and cannot be a cross-goal cache hit.
                if current['status'] in ('certified', 'refuted', 'verified_empty_domain'):
                    cache[key] = index
                items.append(item)
                outcomes.append(current)
                diagnoses.append(diagnosis or dict(stop=current['reason']))
                audit.decisions.append(dict(event='stop_goal', goal=index, status=current['status'], reason=current['reason']))
            if any(r['status'] == 'unresolved' for r in outcomes):
                # Scoped lower models keep the complete PR48 path. Assembly
                # already performed is counted even when the fallback is used.
                with audit.stage('fallback_native_DAG_pack'):
                    payload = presentation.payload(items)
                    packet = dag.pack(payload)
                    audit.counts['expanded_proof_bytes'] = len(canonical(payload).encode())
                    audit.counts['packet_bytes'] = len(canonical(packet).encode())
                with audit.stage('fallback_cold_native_check'):
                    replayed = check(source, batch, packet)
                    require(replayed == outcomes, 'cold checked packet differs from producer results')
            else:
                with audit.stage('finish_direct_dependencies'):
                    packet = assembler.finish()
            result = dict(status='completed', goals=outcomes)
        except Unsupported as exc:
            packet, result = None, dict(status='unsupported', reason=str(exc), goals=[])
        except BudgetStop as exc:
            packet, result = None, dict(status='budget_exhausted', reason=str(exc), goals=[])
    work = audit.report()
    work.update(backend=backend, policy=policy, candidate_language='PR43 questions plus first checked nontrivial goal lemma',
        diagnoses=diagnoses, completed_goals_before_stop=len(outcomes),
        foundations=None if presentation is None else
            dict(scope=presentation.scope(), E=presentation.native(), E_plus=presentation.lemmas()),
        certificate_bytes=0 if packet is None or type(packet) is Emission else len(canonical(packet).encode()),
        emission={} if assembler is None else dict(assembler.accounting(packet if type(packet) is Emission else None),
            path='direct' if type(packet) is Emission else 'scoped_native_fallback' if packet is not None else 'no_delivery',
            intermediate_native_packets=int(packet is not None and type(packet) is not Emission),
            intermediate_native_packet_bytes=0 if packet is None or type(packet) is Emission else len(canonical(packet).encode())),
        term_dag=[] if state is None else state.graph.nodes,
        cross_goal_lemma_reuse=policy == 'reuse')
    return packet, result, work
