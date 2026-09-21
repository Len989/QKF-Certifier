"""Semantic attacks, lifecycle checks, fair controls and cold transport replay."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from research.signed_compact import dag
from research.ground_query.schema import parse
from research.source_query.context import make_request
from research.source_query.fixtures import target
from research.source_query.audit import ForbiddenConstruction
from .context import options, prepare, scope, digest, canonical, load_json, target_context
from .fixtures import cases, goals, MASK, PARITY, batch, DEFAULTS
from .checker import CheckedPresentation, CheckedGoal, open_context, load, check
from .producer import prove
from .terms import ground, roots


class Lemmas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {c['name']: c for c in cases()}
        cls.cache = {}

    def sample(self, name='mask_all_4', route='reuse'):
        key = name, route
        if key not in self.cache:
            c = self.cases[name]
            self.cache[key] = prove(c['source'], c['request'], route=route, limits=c['limits'])
        return deepcopy(self.cache[key])

    def payload(self, name='mask_all_4'):
        return dag.unpack(self.sample(name)[0])

    def reject(self, payload, name='mask_all_4', *, source=None, request=None):
        c = self.cases[name]
        with self.assertRaises((ValueError, TypeError, KeyError, IndexError)):
            check(c['source'] if source is None else source,
                  c['request'] if request is None else request, dag.pack(payload))

    @staticmethod
    def identity(entry):
        entry['id'] = digest({k: v for k, v in entry.items() if k != 'id'})

    @classmethod
    def rebind(cls, payload, new_scope):
        """Repair every superficial identity; semantic proof replay must still hold."""
        out = deepcopy(payload)
        out['scope'] = new_scope
        ids = {}
        for entry in out['E']:
            old = entry['id']
            entry['scope'] = new_scope
            cls.identity(entry)
            ids[old] = entry['id']
        for lemma in out['E_plus']:
            old = lemma['id']
            lemma['scope'] = new_scope
            for kind in ('native', 'lemmas'):
                lemma['basis'][kind] = [ids.get(i, i) for i in lemma['basis'][kind]]
            lemma['via_lemma'] = ids.get(lemma['via_lemma'], lemma['via_lemma'])
            cls.identity(lemma)
            ids[old] = lemma['id']
        for item in out['items']:
            if item['kind'] == 'lemma':
                item['lemma'] = ids[item['lemma']]
            if 'basis' in item:
                for kind in ('native', 'lemmas'):
                    item['basis'][kind] = [ids.get(i, i) for i in item['basis'][kind]]
                item['via_lemma'] = ids.get(item['via_lemma'], item['via_lemma'])
        return out

    def test_registration(self):
        frozen = load_json(Path(__file__).with_name('REGISTRATION.json'))
        protocol = load_json(Path(__file__).with_name('PROTOCOL.json'))
        self.assertEqual(frozen['protocol_sha256'], digest(protocol))
        self.assertEqual(len(self.cases), 21)
        self.assertEqual([x['case_sha256'] for x in frozen['cases']], [digest(c) for c in self.cases.values()])
        self.assertEqual(options(), DEFAULTS)

    def test_sixteen_requests_are_distinct_and_nonconstant(self):
        c = self.cases['mask_all_16']
        self.assertEqual(len({canonical(r) for r in c['request']['requests']}), 16)
        ctx, _ = prepare(c['source'], c['request'])
        from research.signed_predicates.frontend import target_value
        for goal in goals():
            self.assertEqual({target_value(goal, *s) for s in ctx.domain}, {False, True})

    def test_fixed_native_algebra_does_not_depend_on_first_goal(self):
        c = self.cases['mask_all_16']
        ctx, _ = prepare(c['source'], c['request'])
        other = deepcopy(c['request'])
        other['requests'].reverse()
        flipped, _ = prepare(c['source'], other)
        self.assertEqual(scope(ctx), scope(flipped))
        self.assertEqual(ctx.domain, flipped.domain)
        self.assertEqual(ctx.limit, 4)

    def test_E_and_E_plus_are_separate(self):
        payload = self.payload()
        self.assertTrue(payload['E'])
        self.assertEqual(len(payload['E_plus']), 1)
        self.assertTrue(all('evidence' in r and 'certificate' not in r for r in payload['E']))
        self.assertNotIn(payload['E_plus'][0]['claim'], [r['claim'] for r in payload['E']])

    def test_nontrivial_lemma_serves_distinct_consumers(self):
        _, result, work = self.sample()
        self.assertEqual([r['status'] for r in result['goals']], ['certified'] * 4)
        self.assertEqual(work['counts']['lemma_promotions'], 1)
        self.assertEqual(work['counts']['later_goals_using_lemma'], 3)
        lemma = self.payload()['E_plus'][0]
        events = lemma['certificate']['events']
        self.assertGreaterEqual(sum(e['rule'] == 'congruence' for e in events), 1)
        self.assertGreaterEqual(len({e['equation'] for e in events if e['rule'] == 'axiom'}), 2)

    def test_later_proofs_replace_original_derivation(self):
        from research.source_query.encoding import Graph
        from .terms import term
        c = self.cases['mask_all_4']
        for route in ('reuse', 'direct_cache'):
            packet = self.sample(route=route)[0]
            p = dag.unpack(packet)
            context, _ = load(c['source'], c['request'], packet)
            lemma = p['E_plus'][0]
            old_ground = context.request(lemma['claim'], lemma['basis'],
                dict(native=lemma['native_count'], lemmas=lemma['prior_lemmas']))
            def congruences(request, core):
                g = Graph(context.context(), request)
                return {canonical([term(g, e['left']), term(g, e['right'])])
                        for e in core['events'] if e['rule'] == 'congruence'}
            original = congruences(old_ground, lemma['certificate'])
            self.assertTrue(original)
            for request, item in zip(c['request']['requests'][1:], p['items'][1:]):
                self.assertEqual(lemma['id'], item['via_lemma'])
                original_claim = roots(target_context(context.context(), request))
                claim = context.residual_claim(original_claim, item['via_lemma'], item['epoch'])
                self.assertEqual(claim[0], lemma['claim'][1])
                later = context.request(claim, item['basis'], item['epoch'])
                self.assertFalse(original & congruences(later, item['certificate']))

    def test_direct_control_has_same_lemma_and_native_attempts(self):
        _, _, a = self.sample(route='reuse')
        _, _, b = self.sample(route='direct_cache')
        _, _, c = self.sample(route='no_lemmas')
        self.assertEqual(a['fact_attempts'], b['fact_attempts'])
        self.assertEqual(a['fact_attempts'], c['fact_attempts'])
        self.assertEqual(a['foundations']['E_plus'][0]['claim'], b['foundations']['E_plus'][0]['claim'])
        self.assertEqual(c['foundations']['E_plus'], [])

    def test_no_lemma_ablation_repeats_more_congruence_work(self):
        _, _, a = self.sample()
        _, _, b = self.sample(route='no_lemmas')
        self.assertLess(a['counts']['ground_congruence_events'], b['counts']['ground_congruence_events'])

    def test_exact_repeats_get_same_cache_for_every_route(self):
        for route in ('reuse', 'direct_cache', 'no_lemmas'):
            proof, _, work = self.sample('exact_repeats_16', route)
            self.assertEqual(work['counts']['exact_goal_cache_hits'], 15)
            self.assertEqual([x['previous'] for x in dag.unpack(proof)['items'][1:]], [0] * 15)

    def test_trivial_candidate_is_declined_and_later_basis_can_reopen(self):
        _, result, work = self.sample('trivial_native_4')
        self.assertEqual([r['status'] for r in result['goals']], ['certified'] * 4)
        self.assertGreaterEqual(work['counts'].get('declined_lemma_candidates', 0), 1)
        self.assertGreaterEqual(work['counts'].get('native_basis_reopenings', 0), 1)

    def test_arithmetic_lemma_is_source_derived(self):
        p = self.payload('parity_all_1')
        self.assertEqual(len(p['E_plus']), 1)
        self.assertTrue(any(x['evidence']['rule'] == 'low-bit' for x in p['E']))

    def test_fixed_width_is_preserved(self):
        _, result, _ = self.sample('mask_fixed8_1')
        self.assertEqual(result['goals'][0]['width'], dict(kind='fixed', bits=8))
        self.assertFalse(result['goals'][0]['all_positive_widths'])

    def test_no_native_query_after_its_independent_goal_closes(self):
        from . import producer
        c = self.cases['mask_all_4']
        closed = set()
        real_verify, real_derive = CheckedPresentation.verify, producer.derive
        def verify(presentation, request, item):
            checked = real_verify(presentation, request, item)
            if checked.result()['status'] == 'certified':
                closed.add(canonical(request))
            return checked
        def derive(ctx, graph, candidate):
            self.assertNotIn(canonical(ctx.request), closed)
            return real_derive(ctx, graph, candidate)
        with (patch.object(CheckedPresentation, 'verify', verify),
              patch.object(producer, 'derive', derive)):
            _, result, _ = prove(c['source'], c['request'], route='reuse')
        self.assertEqual(len(closed), 4)
        self.assertEqual(len(result['goals']), 4)

    def test_wrong_sources_are_concrete_refutations(self):
        for name in ('mask_wrong_source', 'parity_wrong_source'):
            _, result, work = self.sample(name)
            r = result['goals'][0]
            self.assertEqual(r['status'], 'refuted')
            self.assertTrue(r['source_refutation'])
            self.assertTrue(r['witness']['guard_satisfied'])
            self.assertFalse(work['foundations']['E_plus'])

    def test_representation_gap_is_not_source_refutation(self):
        _, result, work = self.sample('representation_open')
        self.assertEqual(result['goals'][0]['status'], 'unresolved')
        self.assertFalse(result['goals'][0]['source_refutation'])
        self.assertEqual(work['diagnoses'][0]['representation'], 'candidate_policy_exhausted')

    def test_horizon_is_separate(self):
        _, result, _ = self.sample('inactive_horizon')
        self.assertEqual(result['goals'][0]['reason'], 'insufficient_horizon')
        self.assertEqual(result['goals'][0]['ground_relation'], 'inactive_query')

    def test_empty_guard_is_explicit(self):
        _, result, work = self.sample('empty_guard')
        self.assertEqual(result['goals'][0]['status'], 'verified_empty_domain')
        self.assertEqual(work['fact_attempts'], [])

    def test_unsupported_dead_statement_is_not_ignored(self):
        proof, result, _ = self.sample('unsupported_dead_statement')
        self.assertIsNone(proof)
        self.assertEqual(result['status'], 'unsupported')

    def test_budget_batch_has_no_partial_packet(self):
        proof, result, work = self.sample('fact_budget')
        self.assertIsNone(proof)
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertEqual(result['goals'], [])
        self.assertEqual(work['fact_attempts'][0]['outcome'], 'budget_exhausted')

    def test_receipts_cannot_construct_context_or_checked_goal(self):
        with self.assertRaises(ValueError):
            CheckedPresentation()
        with self.assertRaises(ValueError):
            CheckedGoal()
        c = self.cases['mask_all_1']
        context, _ = open_context(c['source'], c['request'])
        with self.assertRaises(ValueError):
            context.promote(dict(status='certified'))

    def test_context_is_immutable_and_unpickleable(self):
        c = self.cases['mask_all_1']
        context, _ = open_context(c['source'], c['request'])
        with self.assertRaises(FrozenInstanceError):
            context._E = '[]'
        with self.assertRaises(TypeError):
            pickle.dumps(context)
        ctx = context.context()
        ctx.guards.clear()
        self.assertTrue(context.context().guards)

    def test_cold_load_rechecks_native_and_lemma_foundations_once(self):
        from . import checker
        c = self.cases['mask_all_4']
        proof = self.sample()[0]
        p = dag.unpack(proof)
        with (patch.object(checker, 'check_native', wraps=checker.check_native) as native,
              patch.object(checker, 'check_ground', wraps=checker.check_ground) as core):
            result = check(c['source'], c['request'], proof)
        self.assertEqual(native.call_count, len(p['E']))
        self.assertEqual(core.call_count, len(p['E_plus']) + 3)
        self.assertEqual(len(result), 4)

    def test_chain_of_checked_lemmas_is_portable(self):
        c = self.cases['mask_all_4']
        p = self.payload()
        context, _ = load(c['source'], c['request'], dag.pack(p))
        handle = context.verify(c['request']['requests'][-1], p['items'][-1])
        extended, lemma = context.promote(handle)
        self.assertEqual(lemma['via_lemma'], p['E_plus'][0]['id'])
        p['E_plus'] = extended.lemmas()
        p['items'][-1] = dict(kind='lemma', lemma=lemma['id'])
        self.assertEqual([r['status'] for r in check(c['source'], c['request'], dag.pack(p))], ['certified'] * 4)

    def test_cannot_promote_handle_from_another_presentation(self):
        c = self.cases['mask_all_4']
        p = self.payload()
        context, _ = load(c['source'], c['request'], dag.pack(p))
        handle = context.verify(c['request']['requests'][-1], p['items'][-1])
        empty, _ = open_context(c['source'], c['request'])
        with self.assertRaisesRegex(ValueError, 'exact previous presentation'):
            empty.promote(handle)

    def test_lemma_self_reference_is_rejected(self):
        p = self.payload()
        lemma = p['E_plus'][0]
        lemma['basis']['lemmas'] = [lemma['id']]
        self.identity(lemma)
        self.reject(p)

    def test_forward_lemma_dependency_is_rejected(self):
        p = self.payload()
        p['E_plus'][0]['prior_lemmas'] = 1
        self.identity(p['E_plus'][0])
        self.reject(p)

    def test_compositional_lemma_cannot_reference_itself(self):
        p = self.payload()
        lemma = p['E_plus'][0]
        lemma['via_lemma'] = lemma['id']
        self.identity(lemma)
        self.reject(p)

    def test_residual_proof_cannot_drop_the_checked_source_lemma(self):
        c = self.cases['mask_all_4']
        p = self.payload()
        context, _ = load(c['source'], c['request'], dag.pack(p))
        item = p['items'][1]
        item['via_lemma'] = None
        ctx = target_context(context.context(), c['request']['requests'][1])
        unproved = context.request(roots(ctx), item['basis'], item['epoch'])
        item['certificate']['request_sha256'] = parse(unproved).identity
        self.reject(p)

    def test_residual_proof_cannot_import_an_unknown_lemma(self):
        p = self.payload()
        p['items'][1]['via_lemma'] = 'forged-checked-receipt'
        self.reject(p)

    def test_native_prefix_cannot_omit_lemma_foundation(self):
        p = self.payload()
        p['E_plus'][0]['native_count'] = 0
        self.identity(p['E_plus'][0])
        self.reject(p)

    def test_negative_ground_checkpoint_is_not_a_lemma(self):
        p = self.payload()
        old = self.sample()[2]['checkpoints'][0]['item']
        lemma = p['E_plus'][0]
        lemma.update(native_count=0, prior_lemmas=0, basis=old['basis'], certificate=old['certificate'])
        self.identity(lemma)
        self.reject(p)

    def test_forged_lemma_conclusion_and_repaired_request_hash_fail(self):
        p = self.payload()
        lemma = p['E_plus'][0]
        lemma['claim'][1] = ['b.true']
        c = self.cases['mask_all_4']
        ctx, _ = prepare(c['source'], c['request'])
        rows = {r['id']: r for r in p['E']}
        premises = [rows[i]['claim'] for i in lemma['basis']['native']]
        lemma['certificate']['request_sha256'] = parse(ground(ctx, premises, lemma['claim'])).identity
        self.identity(lemma)
        self.reject(p)

    def test_missing_native_dependency_fails(self):
        p = self.payload()
        p['E'].pop(0)
        self.reject(p)

    def test_derived_lemma_cannot_be_smuggled_into_native_E(self):
        p = self.payload()
        row = p['E'][0]
        row['evidence'] = dict(rule='lemma', id=p['E_plus'][0]['id'])
        self.identity(row)
        self.reject(p)

    def test_wrong_guard_is_rejected(self):
        r = deepcopy(self.cases['mask_all_4']['request'])
        for q in r['requests']:
            q['guards'] = []
        self.reject(self.payload(), request=r)

    def test_repairing_all_hashes_cannot_weaken_guard_fact(self):
        c = self.cases['mask_all_4']
        r = deepcopy(c['request'])
        for q in r['requests']:
            q['guards'] = []
        ctx, _ = prepare(c['source'], r)
        p = self.rebind(self.payload(), scope(ctx))
        self.reject(p, request=r)

    def test_source_rebinding_is_rejected(self):
        self.reject(self.payload(), source=MASK.replace('(x&7)==0', '(x&7)==1'))

    def test_repairing_all_hashes_cannot_fake_arithmetic_source(self):
        name = 'parity_all_1'
        c = self.cases[name]
        source = PARITY.replace('((x+x)&1)', '((x+1)&1)')
        ctx, _ = prepare(source, c['request'])
        self.reject(self.rebind(self.payload(name), scope(ctx)), name, source=source)

    def test_width_rebinding_is_rejected(self):
        r = deepcopy(self.cases['mask_all_4']['request'])
        for q in r['requests']:
            q['width'] = dict(kind='fixed', bits=8)
        self.reject(self.payload(), request=r)

    def test_native_algebra_and_guarantee_are_bound(self):
        for key, value in (('guarantee', 'universal_schema'), ('profile', 'another_profile')):
            p = self.payload()
            p['scope'][key] = value
            self.reject(p)
        p = self.payload()
        p['scope']['native_algebra']['w.add']['args'] = ['Bool', 'Bool']
        self.reject(p)

    def test_consumer_substitution_is_rejected(self):
        r = deepcopy(self.cases['mask_all_4']['request'])
        r['requests'][0]['target']['goal'] = ['nonnegative']
        self.reject(self.payload(), request=r)

    def test_ground_lemma_does_not_instantiate_as_schema(self):
        p = self.payload()
        p['E_plus'][0]['claim'][0] = ['variable', 'arbitrary_source']
        self.identity(p['E_plus'][0])
        self.reject(p)

    def test_wrong_sort_in_native_term_is_rejected(self):
        p = self.payload()
        row = p['E'][0]
        row['claim'] = [['w.add', ['b.true'], ['b.false']], ['w.c0']]
        self.identity(row)
        self.reject(p)

    def test_native_parity_rows_replayed(self):
        name = 'parity_all_1'
        p = self.payload(name)
        row = next(r for r in p['E'] if r['evidence']['rule'] == 'low-bit')
        row['evidence']['rows'][0]['bits'][0] ^= 1
        self.identity(row)
        self.reject(p, name)

    def test_saved_result_is_not_a_semantic_premise(self):
        p = self.payload()
        p['receipt'] = dict(status='certified')
        self.reject(p)

    def test_corrupted_later_proof_path_fails(self):
        p = self.payload()
        p['items'][1]['certificate']['goals'][0]['path'] = []
        self.reject(p)

    def test_unchecked_future_epoch_fails(self):
        p = self.payload()
        p['items'][1]['epoch']['lemmas'] += 1
        self.reject(p)

    def test_exact_cache_cannot_answer_a_different_target(self):
        p = self.payload()
        p['items'][1] = dict(kind='cached_goal', previous=0)
        self.reject(p)

    def test_exact_cache_cannot_reference_itself(self):
        p = self.payload()
        p['items'][0] = dict(kind='cached_goal', previous=0)
        self.reject(p)

    def test_negative_model_is_not_an_exact_source_cache_hit(self):
        c = self.cases['representation_open']
        request = deepcopy(c['request'])
        request['requests'] *= 2
        _, result, work = prove(c['source'], request, route='reuse')
        self.assertEqual([g['status'] for g in result['goals']], ['unresolved', 'unresolved'])
        self.assertEqual(work['counts'].get('exact_goal_cache_hits', 0), 0)
        self.assertEqual(work['counts']['ground_checkpoints'], 2)
        self.assertEqual(work['counts']['distinct_goals'], 1)

    def test_packet_cannot_reuse_lower_model_as_a_source_verdict(self):
        name = 'representation_open'
        c = self.cases[name]
        request = deepcopy(c['request'])
        request['requests'] *= 2
        p = self.payload(name)
        p['items'].append(dict(kind='cached_goal', previous=0))
        self.reject(p, name, request=request)

    def test_packet_requires_every_independent_goal(self):
        p = self.payload()
        p['items'].pop()
        self.reject(p)

    def test_dag_cycle_and_unreachable_data_rejected(self):
        c = self.cases['mask_all_4']
        packet = self.sample()[0]
        packet['nodes'].append(['l', [len(packet['nodes'])]])
        packet['root'] = len(packet['nodes']) - 1
        with self.assertRaises(ValueError):
            check(c['source'], c['request'], packet)
        packet = self.sample()[0]
        packet['nodes'].append(['v', 'unreachable'])
        with self.assertRaises(ValueError):
            check(c['source'], c['request'], packet)

    def test_all_old_models_are_scoped_and_replayable(self):
        c = self.cases['mask_all_4']
        proof, _, work = self.sample()
        context, _ = load(c['source'], c['request'], proof)
        ids = {r['id'] for r in work['checkpoints']}
        for event in work['decisions']:
            if event['event'] == 'extend_E':
                self.assertIn(event['invalidated_separator'], ids)
        for row in work['checkpoints']:
            self.assertEqual(context.verify(row['request'], row['item']).result(), row['result'])

    def test_stale_lower_model_cannot_use_new_premises(self):
        c = self.cases['mask_all_4']
        proof, _, work = self.sample()
        context, _ = load(c['source'], c['request'], proof)
        old = deepcopy(work['checkpoints'][0]['item'])
        newer = next(r['item'] for r in work['checkpoints'] if r['item']['epoch']['native'] > 0)
        old['basis'], old['epoch'] = newer['basis'], newer['epoch']
        with self.assertRaises(ValueError):
            context.verify(c['request']['requests'][0], old)

    def test_budget_after_E_extension_does_not_export_old_model(self):
        c = self.cases['mask_all_1']
        packet, result, work = prove(c['source'], c['request'], route='reuse', limits=dict(max_rounds=1))
        self.assertIsNone(packet)
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertEqual(len(work['checkpoints']), 1)
        self.assertEqual(len(work['foundations']['E']), 1)

    def test_global_work_budget(self):
        c = self.cases['mask_all_1']
        packet, result, _ = prove(c['source'], c['request'], route='reuse', limits=dict(max_work=0))
        self.assertIsNone(packet)
        self.assertEqual(result['status'], 'budget_exhausted')

    def test_promotion_storage_can_be_disabled_without_losing_proof(self):
        c = self.cases['mask_all_1']
        _, result, work = prove(c['source'], c['request'], route='reuse', limits=dict(max_lemmas=0))
        self.assertEqual(result['goals'][0]['status'], 'certified')
        self.assertFalse(work['foundations']['E_plus'])

    def test_A2_default_keeps_shared_native_cache_without_lemmas(self):
        c = self.cases['mask_all_1']
        _, result, work = prove(c['source'], c['request'])
        self.assertEqual(result['goals'][0]['status'], 'certified')
        self.assertEqual(work['route'], 'no_lemmas')

    def test_unchecked_full_source_construction_is_forbidden(self):
        from . import producer
        from research.signed_coverage.producer import infer
        c = self.cases['mask_all_1']
        ctx, _ = prepare(c['source'], c['request'])
        with patch.object(producer, 'derive', side_effect=lambda *a: infer(c['source'], ctx.selection)):
            with self.assertRaises(ForbiddenConstruction):
                prove(c['source'], c['request'], route='reuse')

    def test_strict_limits(self):
        for value in (dict(max_work=True), dict(max_lemmas=-1), dict(max_lemmas=65), dict(observations=[])):
            with self.assertRaises(ValueError):
                options(value)

    def test_batch_rejects_mixed_scopes_and_observation_lists(self):
        c = self.cases['mask_all_4']
        for key, value in (('guards', []), ('width', dict(kind='fixed', bits=8))):
            r = deepcopy(c['request'])
            r['requests'][1][key] = value
            with self.assertRaises(ValueError):
                prepare(c['source'], r)
        r = deepcopy(c['request'])
        r['observations'] = []
        with self.assertRaises(ValueError):
            prepare(c['source'], r)

    def test_guard_is_checked_on_concrete_witness(self):
        name = 'mask_wrong_source'
        p = self.payload(name)
        p['items'][0]['certificate']['evidence']['input'] = 255
        self.reject(p, name)

    def test_boolean_integer_alias_in_later_guard_is_rejected(self):
        c = self.cases['mask_all_4']
        r = deepcopy(c['request'])
        r['requests'][1]['guards'][0][1] = True
        with self.assertRaises(ValueError):
            prepare(c['source'], r)
        r = deepcopy(c['request'])
        for q in r['requests']:
            q['width'] = dict(kind='fixed', bits=1)
        r['requests'][1]['width']['bits'] = True
        with self.assertRaises(ValueError):
            prepare(c['source'], r)

    def test_boolean_integer_alias_in_packet_scope_is_rejected(self):
        p = self.payload()
        p['scope']['guards'][0][1] = True
        self.reject(p)

    def test_inactive_horizon_cannot_be_relabelled_as_equality(self):
        name = 'inactive_horizon'
        p = self.payload(name)
        p['items'][0] = dict(kind='lemma', lemma='fake')
        self.reject(p, name)

    def test_fresh_normal_and_optimized_checker_without_search(self):
        c = self.cases['mask_all_4']
        raw = json.dumps(dict(source=c['source'], batch=c['request'], packet=self.sample()[0]))
        code = '''import json,sys
from research.source_lemmas.replay import NoSearch
guard=NoSearch()
if guard.loaded():raise ValueError('preloaded search')
sys.meta_path.insert(0,guard)
from research.source_lemmas.checker import check
x=json.load(sys.stdin)
r=check(x['source'],x['batch'],x['packet'])
if guard.loaded():raise ValueError('search imported')
print(json.dumps([g['status'] for g in r]))
'''
        for flags in ([], ['-O']):
            p = subprocess.run([sys.executable, *flags, '-c', code], input=raw, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(json.loads(p.stdout), ['certified'] * 4)

    def test_cli_portable_check_and_exclusive_output(self):
        c = self.cases['mask_all_1']
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'source.java').write_text(c['source'])
            (root/'request.json').write_text(json.dumps(c['request']))
            cmd = [sys.executable, '-m', 'research.source_lemmas', 'prove', str(root/'source.java'),
                   '--request', str(root/'request.json'), '--proof', str(root/'proof.json'), '--route', 'reuse']
            p = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            cmd[3] = 'check'
            p = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            cmd[3] = 'prove'
            p = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(p.returncode, 2)


if __name__ == '__main__':
    unittest.main()
