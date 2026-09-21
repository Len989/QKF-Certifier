from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from research.ground_query.schema import parse
from research.source_query.context import make_request
from research.source_query.fixtures import target, TRUE
from .audit import Audit
from .checker import check
from .context import digest, envelope, load_json, options, prepare
from .fixtures import cases, DEFAULTS
from .producer import prove


class PlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {c['name']: c for c in cases()}
        cls.saved = {}
        for name in ('mask_31', 'double_even', 'goal_true', 'goal_negative', 'power_open',
                     'inactive_horizon', 'bounded_horizon'):
            c = cls.cases[name]
            cls.saved[name] = prove(c['source'], c['request'], limits=c['limits'])

    def run_case(self, name, **kwargs):
        c = self.cases[name]
        return prove(c['source'], c['request'], limits=kwargs.pop('limits', c['limits']),
                     fallback=kwargs.pop('fallback', c['fallback']), **kwargs)

    def reject(self, name, edit, request=None, source=None):
        c = self.cases[name]
        proof = deepcopy(self.saved[name][0])
        edit(proof)
        with self.assertRaises(ValueError):
            check(c['source'] if source is None else source,
                  c['request'] if request is None else request, proof)

    def test_registered_population_and_options(self):
        r = load_json(Path(__file__).with_name('REGISTRATION.json'))
        self.assertEqual(r['protocol_sha256'], digest(load_json(Path(__file__).with_name('PROTOCOL.json'))))
        self.assertEqual([dict(name=c['name'],family=c['family'],case_sha256=digest(c),expected=c['expected']) for c in cases()], r['cases'])
        self.assertEqual(options(None), DEFAULTS)

    def test_mask_questions_generated_from_source_template(self):
        p, r, w = self.saved['mask_31']
        self.assertEqual(r['status'], 'certified')
        self.assertEqual([a['candidate']['rule'] for a in w['fact_attempts']], ['guard-truth', 'eq-mask'])
        q = [d for d in w['decisions'] if d['event'] == 'native_question'][-1]
        self.assertEqual(q['origin']['kind'], 'source_relational_template')
        self.assertIsNotNone(q['origin']['checked_separator'])
        self.assertEqual(len(p['evidence']['facts']), 2)

    def test_low_bit_question_uses_IR_dependency(self):
        _, r, w = self.saved['double_even']
        self.assertEqual(r['status'], 'certified')
        q = next(d for d in w['decisions'] if d['event'] == 'native_question' and d['candidate']['rule'] == 'low-bit')
        self.assertEqual(q['origin']['kind'], 'word_IR_dependency')
        self.assertEqual(q['origin']['ir_node'], q['candidate']['masked_node'])

    def test_changing_consumer_changes_questions(self):
        a, b = self.cases['goal_true'], self.cases['goal_negative']
        self.assertEqual(a['source'], b['source'])
        self.assertEqual(a['request']['guards'], b['request']['guards'])
        first, second = self.saved['goal_true'][2], self.saved['goal_negative'][2]
        ar = [q['candidate']['rule'] for q in first['fact_attempts']]
        br = [q['candidate']['rule'] for q in second['fact_attempts']]
        self.assertIn('low-bit', ar)
        self.assertNotIn('input-bridge', ar)
        self.assertIn('input-bridge', br)
        self.assertNotIn('low-bit', br)

    def test_unused_local_does_not_trigger_native_evaluation(self):
        with patch('research.source_planner.native.parity_evidence', side_effect=AssertionError('irrelevant native query')):
            _, r, w = self.run_case('irrelevant_local')
        self.assertEqual(r['status'], 'certified')
        self.assertEqual([q['candidate'] for q in w['fact_attempts']], [{'rule':'input-bridge','atom':0}])

    def test_full_selected_method_is_still_admitted(self):
        p, r, w = self.run_case('unsupported_dead_statement')
        self.assertIsNone(p)
        self.assertEqual(r['status'], 'unsupported')
        self.assertEqual(w['fact_attempts'], [])

    def test_short_circuit_mask_skips_other_atoms(self):
        _, r, w = self.run_case('mask_short_circuit')
        self.assertEqual(r['status'], 'certified')
        self.assertEqual(sum(q['candidate']['rule']=='eq-mask' for q in w['fact_attempts']), 1)
        self.assertFalse(any(q['candidate']['rule']=='low-bit' for q in w['fact_attempts']))

    def test_short_circuit_parity_asks_one_projection(self):
        _, r, w = self.run_case('parity_short_circuit')
        self.assertEqual(r['status'], 'certified')
        self.assertEqual(sum(q['candidate']['rule']=='low-bit' for q in w['fact_attempts']), 1)

    def test_collapsed_context_keeps_remaining_source_template(self):
        _, r, w = self.run_case('mask_two')
        self.assertEqual(r['status'], 'certified')
        pairs = [(q['candidate']['antecedent'], q['candidate']['consequent']) for q in w['fact_attempts'] if q['candidate']['rule']=='eq-mask']
        self.assertEqual(pairs, [(0,1),(2,3)])

    def test_no_native_questions_after_checked_closure(self):
        from . import producer
        original_check, original_fact = producer.check, Audit.fact
        closed = [False]
        def checked(*args):
            r = original_check(*args)
            if r['status'] == 'certified':closed[0] = True
            return r
        def fact(audit, *args):
            self.assertFalse(closed[0], 'native call after a sufficient proof')
            return original_fact(audit, *args)
        with patch.object(producer, 'check', checked), patch.object(Audit, 'fact', fact):
            _, r, _ = self.run_case('parity_short_circuit')
        self.assertEqual(r['status'], 'certified')

    def test_runtime_closed_guard(self):
        audit = Audit(options(None))
        audit.closed = True
        with self.assertRaises(ValueError):audit.fact({'rule':'guard-zero'}, lambda: None)

    def test_candidate_ranking_does_not_evaluate_native_rules(self):
        from .language import State
        c = self.cases['mask_31']
        ctx = prepare(c['source'], c['request'])
        state = State(ctx, Audit(options(None)))
        with (patch('research.source_query.rules.mask_implication', side_effect=AssertionError('peek')),
             patch('research.source_query.rules.parity_evidence', side_effect=AssertionError('peek')),
             patch('research.source_query.rules.input_bridge', side_effect=AssertionError('peek'))):
            self.assertIsNotNone(state.next_question())

    def test_separator_orders_sufficient_congruence_pullbacks(self):
        source = 'class Demo {static boolean f(long x) {return x<0 && x!=0;}}'
        req = make_request(target(['and',['negative'],['not',['popcount_eq',0]]]))
        _, r, w = prove(source, req)
        self.assertEqual(r['status'], 'certified')
        self.assertGreater(w['counts']['separator_term_evaluations'], 0)
        origins = [d['origin'] for d in w['decisions'] if d['event']=='native_question']
        self.assertTrue(any(o.get('via')=='sufficient_congruence_pullback' for o in origins))

    def test_model_invalidation_after_every_E_extension(self):
        _, _, w = self.saved['double_even']
        known = {p['id']:p for p in w['checkpoints']}
        version, active = 0, None
        for event in w['decisions']:
            if event['event']=='checked_obligation':
                self.assertEqual(event['E_version'], version)
                active = event['id'] if event['status']=='unresolved' else None
            elif event['event']=='extend_E':
                self.assertEqual(event['invalidated_separator'], active)
                self.assertEqual(known[active]['E_version'], version)
                version += 1
                self.assertEqual(event['version'], version)
                active = None
            elif event['event']=='native_question':
                self.assertEqual(event['origin']['E_version'], version)
                self.assertEqual(event['origin']['checked_separator'], active)
        self.assertEqual(w['counts']['invalidated_separators'], len([d for d in w['decisions'] if d['event']=='extend_E']))

    def test_historical_models_replay_only_their_E(self):
        c = self.cases['double_even']
        _, _, w = self.saved['double_even']
        for p in w['checkpoints']:
            self.assertEqual(check(c['source'],c['request'],p['certificate']),p['result'])

    def test_old_model_rejected_after_E_extension(self):
        c = self.cases['double_even']
        old, new = self.saved['double_even'][2]['checkpoints'][:2]
        forged = deepcopy(new['certificate'])
        forged['evidence']['certificate'] = deepcopy(old['certificate']['evidence']['certificate'])
        with self.assertRaises(ValueError):check(c['source'], c['request'], forged)

    def test_rebinding_old_model_hash_does_not_validate_new_E(self):
        c = self.cases['double_even']
        old, new = self.saved['double_even'][2]['checkpoints'][:2]
        forged = deepcopy(new['certificate'])
        forged['evidence']['certificate'] = deepcopy(old['certificate']['evidence']['certificate'])
        forged['evidence']['certificate']['request_sha256'] = parse(forged['evidence']['request']).identity
        with self.assertRaises(ValueError):check(c['source'], c['request'], forged)

    def test_failed_native_questions_are_retained(self):
        _, _, w = self.saved['double_even']
        self.assertTrue(any(q['outcome']=='not_applicable' for q in w['fact_attempts']))
        keys = [digest(q['candidate']) for q in w['fact_attempts']]
        self.assertEqual(len(keys),len(set(keys)))

    def test_eager_control_is_not_labelled_adaptive(self):
        _, r, w = self.run_case('irrelevant_local',route='eager')
        self.assertEqual(r['status'],'certified')
        self.assertFalse(w['automatic_observation_planner'])
        self.assertGreater(len(w['fact_attempts']),1)

    def test_ordinary_control_gets_identical_questions(self):
        _, r, w = self.run_case('double_even',route='ordinary')
        self.assertEqual(r['status'],'certified')
        self.assertEqual(w['fact_attempts'],self.saved['double_even'][2]['fact_attempts'])
        self.assertTrue(all(c['backend']=='ordinary_full_CC' for c in w['checkpoints']))

    def test_inactive_query_is_not_a_model(self):
        p,r,w = self.saved['inactive_horizon']
        self.assertEqual(p['kind'],'inactive')
        self.assertEqual(r['ground_relation'],'inactive_query')
        self.assertEqual(r['reason'],'insufficient_horizon')
        self.assertNotIn('certificate',p['evidence'])
        self.assertEqual(w['fact_attempts'],[])

    def test_inactive_query_reports_endpoint_not_full_E_depth(self):
        p,r,_ = self.run_case('irrelevant_local',route='eager',limits={'max_horizon':0})
        self.assertEqual(p['kind'],'inactive')
        self.assertEqual(r['required_horizon'],1)
        self.assertGreater(r['final_horizon'],r['required_horizon'])

    def test_inactive_label_on_active_query_rejected(self):
        self.reject('inactive_horizon',lambda p:p['evidence'].update(horizon=128))

    def test_bounded_nonvisibility_is_not_nonconsequence(self):
        p,r,_ = self.saved['bounded_horizon']
        self.assertEqual(p['kind'],'ground')
        self.assertEqual(r['ground_relation'],'not_visible')
        self.assertEqual(r['reason'],'insufficient_horizon')
        self.assertLess(r['ground_result']['horizon'],r['ground_result']['final_horizon'])

    def test_bounded_model_cannot_claim_final_nonconsequence(self):
        self.reject('bounded_horizon',lambda p:p['evidence']['certificate']['goals'][0].update(status='not_entailed'))

    def test_bool_horizon_rejected(self):
        self.reject('inactive_horizon',lambda p:p['evidence'].update(horizon=False))

    def test_grows_horizon_before_more_source_questions(self):
        _,r,w = self.run_case('bounded_horizon',limits={'max_horizon':128})
        self.assertEqual(r['status'],'refuted')
        self.assertTrue(any(d['event']=='grow_horizon' for d in w['decisions']))
        grow=next(i for i,d in enumerate(w['decisions']) if d['event']=='grow_horizon')
        self.assertEqual(w['decisions'][grow+1]['event'],'checked_obligation')

    def test_positive_proof_can_stop_below_full_horizon(self):
        _,r,w = self.run_case('irrelevant_local',route='eager')
        self.assertEqual(r['status'],'certified')
        self.assertLess(r['ground_result']['horizon'],r['ground_result']['final_horizon'])
        self.assertFalse(any(d['event']=='grow_horizon' for d in w['decisions']))

    def test_representation_gap_is_not_a_source_violation(self):
        _,r,w = self.saved['power_open']
        self.assertEqual(r['status'],'unresolved')
        self.assertEqual(r['reason'],'not_entailed_from_current_E')
        self.assertFalse(r['source_refutation'])
        self.assertEqual(w['diagnosis']['representation'],'candidate_language_exhausted')
        self.assertEqual(w['counts'].get('legacy_builder_calls',0),0)

    def test_refusal_and_questions_are_reproducible(self):
        p,r,w = self.run_case('power_open')
        oldp,oldr,oldw=self.saved['power_open']
        self.assertEqual(r,oldr)
        self.assertEqual(w['diagnosis'],oldw['diagnosis'])
        self.assertEqual(w['fact_attempts'],oldw['fact_attempts'])
        self.assertEqual(p['evidence']['request'],oldp['evidence']['request'])

    def test_wrong_source_does_not_inherit_desired_true(self):
        p,r,w = self.run_case('mask_mutant')
        self.assertEqual(r['status'],'refuted')
        self.assertEqual(p['kind'],'legacy')
        self.assertEqual(p['evidence']['proof']['kind'],'witness')
        self.assertEqual(r['reason'],'concrete_violation')
        self.assertTrue(w['checkpoints'])

    def test_guard_is_not_dropped_for_witness(self):
        p,r,_ = self.run_case('arithmetic_guarded_mutant')
        self.assertEqual(r['status'],'refuted')
        p['evidence']['proof']['evidence']={'width':2,'input':0}
        c=self.cases['arithmetic_guarded_mutant']
        with self.assertRaises(ValueError):check(c['source'],c['request'],p)

    def test_explicit_fallback_pays_prior_attempts(self):
        p,r,w = self.run_case('power_guarded_fallback')
        self.assertEqual(r['status'],'certified')
        self.assertEqual(r['reason'],'explicit_covered_fallback')
        self.assertEqual(p['evidence']['proof']['kind'],'covered')
        self.assertGreater(w['counts']['legacy_builder_calls'],0)
        self.assertGreater(next(d['prior_fact_attempts'] for d in w['decisions'] if d['event']=='explicit_fallback'),0)
        self.assertTrue(w['checkpoints'])

    def test_fallback_budget_keeps_prior_work_without_partial_proof(self):
        p,r,w=self.run_case('power_guarded_fallback',limits={'max_source_states':1})
        self.assertIsNone(p)
        self.assertEqual(r['status'],'budget_exhausted')
        self.assertTrue(w['checkpoints'])
        self.assertGreater(w['counts']['native_rule_attempts'],0)

    def test_question_budget_never_exports_partial_result(self):
        p,r,w=self.run_case('fact_budget')
        self.assertIsNone(p)
        self.assertEqual(r['status'],'budget_exhausted')
        self.assertEqual(w['fact_attempts'][0]['outcome'],'budget_exhausted')

    def test_round_budget_does_not_reuse_stale_negative_model(self):
        p,r,w=self.run_case('double_even',limits={'max_rounds':1})
        self.assertIsNone(p)
        self.assertEqual(r['status'],'budget_exhausted')
        self.assertEqual(w['E_version'],1)
        self.assertEqual(w['checkpoints'][-1]['E_version'],0)
        self.assertIsNotNone(next(d['invalidated_separator'] for d in w['decisions'] if d['event']=='extend_E'))

    def test_global_budget_is_charged_before_source_admission(self):
        p,r,w=self.run_case('double_even',limits={'max_work':0})
        self.assertIsNone(p)
        self.assertEqual(r['status'],'budget_exhausted')
        self.assertEqual(w['fact_attempts'],[])

    def test_empty_guard_is_explicit(self):
        p,r,w=self.run_case('empty_guard')
        self.assertEqual(r['status'],'verified_empty_domain')
        self.assertEqual(p['evidence']['proof']['kind'],'empty')
        self.assertEqual(w['fact_attempts'],[])

    def test_guard_binding_cannot_be_relabelled(self):
        c=self.cases['goal_negative']
        req=deepcopy(c['request']);req['guards']=[['nonnegative']]
        self.reject('goal_negative',lambda p:p.update(binding=envelope(prepare(c['source'],req),'ground',{})['binding']),request=req)

    def test_source_binding_cannot_be_relabelled(self):
        c=self.cases['mask_31'];source=c['source'].replace('2147483648L','3')
        self.reject('mask_31',lambda p:p.update(binding=envelope(prepare(source,c['request']),'ground',{})['binding']),source=source)

    def test_fixed_width_fact_cannot_be_promoted_to_all_widths(self):
        c=self.cases['mask_fixed_alias'];p,_,_=self.run_case('mask_fixed_alias')
        req=deepcopy(c['request']);req['width']={'kind':'all_positive'}
        p['binding']=envelope(prepare(c['source'],req),'ground',{})['binding']
        with self.assertRaises(ValueError):check(c['source'],req,p)

    def test_corrupted_native_bit_proof(self):
        def edit(p):
            f=next(f for f in p['evidence']['facts'] if f['rule']=='low-bit')
            f['rows'][-1]['bits']=[1,1]
        self.reject('double_even',edit)

    def test_missing_native_provenance(self):
        self.reject('mask_31',lambda p:p['evidence']['facts'].pop())

    def test_receipt_cannot_replace_native_fact(self):
        self.reject('mask_31',lambda p:p['evidence']['facts'][0].update(checked=True))

    def test_ground_query_cannot_be_replaced(self):
        def edit(p):
            q=p['evidence']['request']['queries'][0];q[0]=q[1]
        self.reject('mask_31',edit)

    def test_false_ground_proof_path(self):
        self.reject('double_even',lambda p:p['evidence']['certificate']['goals'][0].update(path=[]))

    def test_false_model_cannot_certify_source_violation(self):
        self.reject('power_open',lambda p:p['evidence']['certificate']['goals'][0].update(status='equal'))

    def test_fabricated_native_conclusion_is_checked_before_acceptance(self):
        c=self.cases['double_even']
        def bad(ctx,g,candidate):
            return {'rule':'guard-truth','term':g.target()},(g.source(),g.literal(True))
        with patch('research.source_planner.native.derive',bad),self.assertRaises(ValueError):
            prove(c['source'],c['request'])

    def test_hidden_full_source_construction_is_forbidden(self):
        from research.source_query.audit import ForbiddenConstruction
        def hidden(ctx,g,candidate):
            from research.signed_coverage.producer import infer
            return infer('invalid',{})
        c=self.cases['double_even']
        with patch('research.source_planner.native.derive',hidden),self.assertRaises(ForbiddenConstruction):
            prove(c['source'],c['request'])

    def test_no_phase_forcing_transferred_to_signed_profile(self):
        w=self.saved['double_even'][2]
        self.assertFalse(w['paper_I_forcing'])
        self.assertFalse(any('pure_rows' in name or 'source_forcing' in name for name in w['calls']))

    def test_user_cannot_supply_an_observation_list(self):
        with self.assertRaises(ValueError):options({'observations':[]})
        with self.assertRaises(ValueError):options({'max_horizon':False})

    def test_duplicate_wire_json_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'duplicate.json';p.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError):load_json(p)

    def test_fresh_replay_without_planner_or_search(self):
        script='''
import json,sys
from research.source_planner.replay import NoSearch
guard=NoSearch();sys.meta_path.insert(0,guard)
from research.source_planner.checker import check
data=json.load(open(sys.argv[1]))
for item in data:
 if check(item['source'],item['request'],item['proof'])!=item['result']:raise RuntimeError('proof')
if guard.loaded():raise RuntimeError('search imported')
'''
        records=[]
        for name in ('double_even','power_open','inactive_horizon','bounded_horizon'):
            p,r,_=self.saved[name];c=self.cases[name]
            records.append(dict(source=c['source'],request=c['request'],proof=p,result=r))
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'proofs.json';path.write_text(json.dumps(records))
            for flags in ([],['-O']):
                proc=subprocess.run([sys.executable,*flags,'-c',script,str(path)],capture_output=True,text=True)
                self.assertEqual(proc.returncode,0,proc.stderr)

    def test_cli_goal_budget_and_exclusive_proof(self):
        c=self.cases['double_even']
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'Demo.java';req=root/'request.json';proof=root/'proof.json'
            source.write_text(c['source']);req.write_text(json.dumps(c['request']))
            args=[str(source),'--request',str(req),'--proof',str(proof)]
            prefix=[sys.executable,'-m','research.source_planner']
            first=subprocess.run(prefix+['prove']+args,capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stderr)
            again=subprocess.run(prefix+['prove']+args,capture_output=True,text=True)
            self.assertEqual(again.returncode,2)
            replay=subprocess.run(prefix+['check']+args,capture_output=True,text=True)
            self.assertEqual(replay.returncode,0,replay.stderr)


if __name__ == '__main__':
    unittest.main()
