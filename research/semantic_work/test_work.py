"""Contract corruption, accounting controls, and independent source-proof replay."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from .contract import (PROFILE, canonical, digest, load_json, make_request, request, save_json)
from .evidence import (NativeFact, AbstractSeparator, ConcreteWitness, Unresolved,
                       native_fact, abstract_separator, concrete_witness, unresolved, refutation)
from .fixtures import cases, target
from .meter import Meter, StopWork, ForbiddenWork
from .run import run, check, execute

ROOT = Path(__file__).resolve().parents[2]
ROWS = dict(cases())


class ContractTests(unittest.TestCase):
    def test_registered_inputs_bound(self):
        reg = load_json(Path(__file__).with_name('REGISTRATION.json'))
        self.assertEqual(reg['cases'], [{'name': n, 'request_sha256': digest(r)} for n, r in cases()])
    def test_all_guarantees_explicit(self):
        for g in ('consumer_sufficient', 'exact_source_interface', 'minimal_source_interface'):
            r = deepcopy(ROWS['constant_true']); r['guarantee'] = g
            self.assertEqual(request(r)['guarantee'], g)
    def test_selection_mismatch(self):
        r = deepcopy(ROWS['constant_true']);r['selection']['word_type'] = 'int'
        with self.assertRaises(ValueError):request(r)
    def test_profile_mismatch(self):
        r = deepcopy(ROWS['constant_true']);r['profile'] = 'java-without-guards'
        with self.assertRaises(ValueError):request(r)
    def test_target_not_from_method_name(self):
        r = deepcopy(ROWS['constant_true']);r['consumer']['target']['goal'] = ['negative']
        self.assertNotEqual(digest(request(r)), digest(ROWS['constant_true']))
    def test_unknown_and_missing_fields(self):
        for change in (lambda r:r.update(cache_success=True), lambda r:r.pop('guarantee')):
            r = deepcopy(ROWS['constant_true']);change(r)
            with self.assertRaises(ValueError):request(r)
    def test_nonboolean_integer_budget(self):
        for val in (True, -1, 1.0, '3'):
            r=deepcopy(ROWS['constant_true']);r['budget']['max_work']=val
            with self.assertRaises(ValueError):request(r)
    def test_old_caps_not_increased(self):
        r=deepcopy(ROWS['constant_true']);r['budget']['backend']['max_states']=65
        with self.assertRaises(ValueError):request(r)
    def test_conditions_are_not_silently_assumed(self):
        x=run(ROWS['unsupported_condition'])
        self.assertEqual(x['result']['status'], 'unsupported_conditions');self.assertIsNone(x['proof'])
        self.assertNotIn('coverage_build_attempts', x['work']['counts'])
    def test_conditions_validated(self):
        r=deepcopy(ROWS['constant_true']);r['conditions']=[['made_up']]
        with self.assertRaises(ValueError):request(r)
    def test_float_code_tuple_cycle_rejected(self):
        cyc=[];cyc.append(cyc)
        for x in (float('nan'), 1.0, lambda: None, (0,), cyc, {0:1}):
            with self.assertRaises(ValueError):canonical(x)
    def test_depth_and_integer_limits(self):
        a=0
        for _ in range(100):a=[a]
        for x in (a, 1<<8193):
            with self.assertRaises(ValueError):canonical(x)
    def test_duplicate_json_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.json';p.write_text('{"x":1,"x":2}')
            with self.assertRaises(ValueError):load_json(p)
            with self.assertRaises(FileExistsError):save_json(p, {'ok':True})
            self.assertEqual(p.read_text(), '{"x":1,"x":2}')
    def test_detached_request(self):
        r=deepcopy(ROWS['constant_true']);x=request(r);r['consumer'].clear()
        self.assertEqual(x, ROWS['constant_true'])


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = ROWS['power_long'];cls.good=run(cls.r)
    def test_old_verdict_and_proof_exact(self):
        from research.unified.v6 import prove
        r,p=prove(self.r['source'],self.r['consumer']['target'])
        self.assertEqual(self.good['result']['legacy_result'],r)
        self.assertEqual(self.good['proof']['legacy'],p)
    def test_new_replay_and_old_checker(self):
        from research.unified.v6 import check as old
        self.assertEqual(check(self.r,self.good['proof']),self.good['result'])
        self.assertEqual(old(self.r['source'],self.r['consumer']['target'],self.good['proof']['legacy']),
                         self.good['result']['legacy_result'])
    def test_counts_match_constructed_data(self):
        proof=self.good['proof']['legacy']['proof']['observations'];counts=self.good['work']['counts']
        self.assertEqual(counts['discovered_states'],len(proof['source_model']['states']))
        self.assertEqual(counts['completed_discovery_branches'],len(proof['source_model']['edges']))
        self.assertEqual(counts['observation_questions_created'],len(proof['observations']['predicates']))
        self.assertEqual(counts['separators_materialized'],len(proof['observations']['separators']))
    def test_rechecks_not_hidden(self):
        c=self.good['work']['counts']
        self.assertGreater(c['source_parse_completions'],1)
        self.assertGreater(c['coverage_edge_rechecks'],c['completed_discovery_branches'])
        self.assertGreater(c['ir_word_nodes_produced_total'],c['unique_ir_word_nodes'])
    def test_unknown_metrics_not_fake_zeros(self):
        w=self.good['work']
        self.assertIsNone(w['ground_input_terms']);self.assertIsNone(w['added_ground_terms'])
        self.assertFalse(w['is_certificate']);self.assertEqual(w['lemma_reuses'],0)
    def test_telemetry_tampering_does_not_prove_semantics(self):
        x=deepcopy(self.good);x['work']['counts'].clear()
        self.assertEqual(check(self.r,x['proof']),self.good['result'])
        x['proof']['result']['status']='refuted'
        with self.assertRaises(Exception):check(self.r,x['proof'])
    def test_source_binding(self):
        r=deepcopy(self.r);r['source']+=' '
        with self.assertRaises(Exception):check(r,self.good['proof'])
    def test_target_binding(self):
        r=deepcopy(self.r);r['consumer']['target']['goal']=['negative']
        with self.assertRaises(Exception):check(r,self.good['proof'])
    def test_rehashed_false_target_still_fails(self):
        r=deepcopy(self.r);r['consumer']['target']['goal']=['negative']
        p=deepcopy(self.good['proof']);p['request_sha256']=digest(r)
        with self.assertRaises(Exception):check(r,p)
    def test_receipt_cannot_replace_proof(self):
        p=deepcopy(self.good['proof']);p['legacy']={'status':'certified'}
        with self.assertRaises(Exception):check(self.r,p)
    def test_zero_global_budget(self):
        r=deepcopy(self.r);r['budget']['max_work']=0
        x=run(r);self.assertEqual(x['result']['status'],'budget_exhausted');self.assertIsNone(x['proof'])
    def test_mid_construction_abort_keeps_partial_work(self):
        r=deepcopy(self.r);r['budget']['max_work']=2000
        x=run(r);self.assertIsNone(x['proof']);self.assertEqual(x['work']['counts']['work_calls'],2001)
        self.assertGreaterEqual(x['work']['counts'].get('coverage_build_attempts',0),1)
    def test_covered_budget_keeps_discovered_states(self):
        r=deepcopy(self.r);r['budget']['backend']['max_states']=2
        x=run(r);self.assertIsNone(x['proof'])
        self.assertEqual(x['work']['counts']['discovered_states'],2)
        self.assertGreater(x['work']['counts']['discovery_branch_attempts'],x['work']['counts']['completed_discovery_branches'])
    def test_fallback_keeps_precheck_cost(self):
        r=deepcopy(self.r);r['strategy']='witness_then_covered';r['search']={'max_width':1,'max_evaluations':2}
        x=run(r);c=x['work']['counts']
        self.assertEqual(x['result']['status'],'certified');self.assertEqual(c['route_attempts'],2)
        self.assertEqual(c['fallbacks'],1);self.assertGreaterEqual(c['whole_word_evaluation_calls'],2)
        self.assertEqual(x['work']['phases'][1]['search']['evaluations'],2)
    def test_fallback_cannot_reset_attempt_budget(self):
        r=deepcopy(self.r);r['strategy']='witness_then_covered';r['search']={'max_width':0,'max_evaluations':0}
        r['budget']['max_attempts']=1
        x=run(r);self.assertIsNone(x['proof']);self.assertEqual(x['result']['status'],'budget_exhausted')
        self.assertEqual(x['work']['counts']['route_attempts'],2)
    def test_witness_without_source_factor(self):
        r=deepcopy(ROWS['delayed_31']);r['strategy']='witness_then_covered'
        x=run(r,forbid_full=True)
        self.assertEqual(x['result']['route'],'concrete-v1');self.assertEqual(x['result']['status'],'refuted')
        self.assertNotIn('coverage_build_attempts',x['work']['counts'])
        self.assertEqual(check(r,x['proof']),x['result'])
    def test_late_witness_falls_back_not_certified(self):
        r=deepcopy(ROWS['late_witness']);r['strategy']='witness_then_covered';r['search']={'max_width':1,'max_evaluations':2}
        x=run(r);self.assertEqual(x['result']['route'],'covered-v6');self.assertEqual(x['result']['status'],'refuted')
        self.assertEqual(x['result']['legacy_result']['inner']['target']['witness_width'],10)
    def test_measured_size_is_full_proof(self):
        self.assertEqual(self.good['certificate_bytes'],len(canonical(self.good['proof']).encode()))
    def test_unsupported_source_is_not_success(self):
        x=run(ROWS['unsupported_shift']);self.assertEqual(x['result']['status'],'unsupported');self.assertIsNone(x['proof'])
    def test_exact_and_minimal_guarantee_not_downgraded(self):
        r=deepcopy(ROWS['constant_true']);r['guarantee']='minimal_source_interface'
        x=run(r);self.assertEqual(x['result']['achieved']['source_interface'],'exact_and_minimal_finite_model')
    def test_fresh_replay_without_meter_or_producers(self):
        code='''import sys,json,importlib.abc
sys.path.insert(0,sys.argv[1])
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self,n,path=None,target=None):
  if n in ('subprocess','platform','z3','cvc5','research.semantic_work.meter') or (n.startswith('research.') and n.rsplit('.',1)[-1].startswith('producer')):raise ImportError(n)
sys.meta_path.insert(0,Guard())
from research.semantic_work.run import check
r,p,expected=json.load(open(sys.argv[2]))
if check(r,p)!=expected:raise RuntimeError('semantic replay differs')
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.json';save_json(p,[self.r,self.good['proof'],self.good['result']])
            for flags in ([],['-O']):
                x=subprocess.run([sys.executable,*flags,'-I','-S','-B','-c',code,str(ROOT),str(p)],capture_output=True,text=True)
                self.assertEqual(x.returncode,0,x.stderr)


class MeterTests(unittest.TestCase):
    def test_hidden_full_builder_alias_is_caught(self):
        from research.signed_bridge.producer import derive as alias
        r=ROWS['constant_true'];m=Meter(forbid_full=True)
        with self.assertRaises(ForbiddenWork):
            with m:
                with m.stage('hidden',attempt=True):alias(r['source'],r['selection'])
        self.assertEqual(m.report['counts']['old_full_builder_calls'],1)
        self.assertIsNone(sys.getprofile())
    def test_covered_route_does_not_call_full_builder(self):
        self.assertEqual(run(ROWS['constant_true'],forbid_full=True)['result']['status'],'certified')
    def test_repeated_attempts_are_additive(self):
        r=ROWS['constant_true'];m=Meter()
        with m:
            a,_=execute(r,m);before=m.counts['discovered_states']
            b,_=execute(r,m)
        self.assertEqual(a,b);self.assertEqual(m.counts['discovered_states'],2*before)
        self.assertEqual(m.counts['route_attempts'],2)
    def test_real_verified_fact_cache_hit_not_hidden(self):
        r=ROWS['constant_true'];m=Meter();cache={}
        with m:
            with m.stage('native_requests'):
                for _ in range(2):
                    key=[digest(r),0,1];m.fact_request(key,cache_hit=bool(cache))
                    if not cache:cache['fact']=native_fact(r,0,1,True)
        self.assertEqual(m.counts['fact_requests'],2);self.assertEqual(m.counts['unique_fact_requests'],1)
        self.assertEqual(m.counts['direct_fact_attempts'],1);self.assertEqual(m.counts['fact_cache_hits'],1)
        self.assertEqual(m.counts['whole_word_evaluation_calls'],1)
    def test_nested_profiler_rejected(self):
        with Meter():
            with self.assertRaises(ValueError):
                with Meter():pass
    def test_exceptions_restore_profiler_and_trace(self):
        import tracemalloc
        with self.assertRaises(RuntimeError):
            with Meter() as m:
                with m.stage('failure'):raise RuntimeError('test')
        self.assertIsNone(sys.getprofile());self.assertFalse(tracemalloc.is_tracing())
    def test_phase_sum_not_double_counted(self):
        x=run(ROWS['constant_true']);s={}
        for phase in x['work']['phases']:
            for k,v in phase['counts'].items():s[k]=s.get(k,0)+v
        self.assertEqual(s,x['work']['counts'])


class EvidenceTests(unittest.TestCase):
    def test_native_fact_scope(self):
        f=native_fact(ROWS['constant_true'],0,1,True)
        self.assertIs(type(f),NativeFact);self.assertFalse(f.data()['target_checked'])
        self.assertFalse(f.data()['all_positive_widths'])
    def test_bad_native_fact_rejected(self):
        with self.assertRaises(ValueError):native_fact(ROWS['constant_true'],0,1,False)
    def test_native_fact_exact_width(self):
        with self.assertRaises(ValueError):native_fact(ROWS['constant_true'],2,1,True)
    def test_separator_is_not_program_counterexample(self):
        from research.pure_rows.fixtures import examples
        from research.pure_rows.producer import prove
        p=dict(examples())['I_6_2_obstruction'];_,cert=prove(p)
        e=abstract_separator(p,cert,0,2,1)
        self.assertIs(type(e),AbstractSeparator);self.assertFalse(e.data()['source_refutation'])
        with self.assertRaises(ValueError):refutation(e)
        with self.assertRaises(ValueError):abstract_separator(p,cert,0,2,2)
    def test_only_concrete_witness_refutes(self):
        from research.signed_witness.producer import from_raw
        r=ROWS['delayed_31'];p,_=from_raw(r['source'],r['consumer']['target'],0,1)
        e=concrete_witness(r,p);self.assertIs(type(e),ConcreteWitness)
        self.assertEqual(refutation(e)['witness_width'],1)
    def test_fake_evidence_constructor_and_pickle(self):
        for cls in (NativeFact,ConcreteWitness,AbstractSeparator,Unresolved):
            with self.assertRaises(ValueError):cls(kind='concrete_witness',payload={'status':'refuted'})
        e=unresolved('not_refuted',{})
        with self.assertRaises(TypeError):pickle.dumps(e)
        with self.assertRaises(ValueError):refutation(e)
    def test_evidence_detached(self):
        e=unresolved('budget_exhausted',{'attempt':1});x=e.data();x['target_checked']=True
        self.assertFalse(e.data()['target_checked'])
    def test_presentation_receipt_not_separator(self):
        with self.assertRaises(Exception):abstract_separator({}, {'status':'certified'},0,1,1)


class AdditionalBoundaryTests(unittest.TestCase):
    def test_fallback_phase_totals(self):
        r=deepcopy(ROWS['power_long']);r['strategy']='witness_then_covered'
        r['search']={'max_width':1,'max_evaluations':2}
        w=run(r)['work'];counts={}
        for phase in w['phases']:
            for k,v in phase['counts'].items():counts[k]=counts.get(k,0)+v
        self.assertEqual(counts,w['counts'])
    def test_zero_attempt_budget(self):
        r=deepcopy(ROWS['constant_true']);r['budget']['max_attempts']=0
        x=run(r);self.assertIsNone(x['proof'])
        self.assertNotIn('coverage_build_attempts',x['work']['counts'])
    def test_work_budget_spans_repeated_execute(self):
        r=ROWS['constant_true'];m=Meter()
        with self.assertRaises(StopWork):
            with m:
                execute(r,m);m.max_work=m.counts['work_calls']+5
                execute(r,m)
        self.assertEqual(m.report['counts']['route_attempts'],2)
        self.assertEqual(m.report['counts']['work_calls'],m.max_work+1)
    def test_guard_levels_do_not_become_semantic_assumptions(self):
        r=ROWS['constant_true'];x=run(r)
        q=deepcopy(r);q['conditions']=[['positive']]
        p=deepcopy(x['proof']);p['request_sha256']=digest(q)
        with self.assertRaises(Exception):check(q,p)
    def test_unknown_proof_route_rejected(self):
        r=ROWS['constant_true'];p=run(r)['proof'];p['route']='cached-success'
        with self.assertRaises(ValueError):check(r,p)
    def test_source_fact_not_target_certificate(self):
        r=ROWS['constant_true'];f=native_fact(r,0,1,True)
        with self.assertRaises(ValueError):check(r,f.data())
    def test_cli_run_check_and_exclusive(self):
        from .cli import main
        from contextlib import redirect_stdout,redirect_stderr
        import io
        with tempfile.TemporaryDirectory() as d,redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
            root=Path(d);r=root/'r.json';out=root/'run.json';proof=root/'p.json'
            save_json(r,ROWS['constant_true'])
            self.assertEqual(main(['run',str(r),'--output',str(out)]),0)
            report=load_json(out);save_json(proof,report['proof'])
            self.assertEqual(main(['check',str(r),'--proof',str(proof),'--output',str(root/'checked.json')]),0)
            self.assertEqual(main(['run',str(r),'--output',str(out)]),64)
    def test_extra_proof_receipt_rejected(self):
        r=ROWS['constant_true'];p=run(r)['proof'];p['cached_success']=True
        with self.assertRaises(ValueError):check(r,p)


if __name__ == '__main__':
    unittest.main()
