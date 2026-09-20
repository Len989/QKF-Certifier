"""Contract, mutation, reuse, historical replay and import-isolation tests."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import importlib
import json
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from research.signed_bridge.model import request
from research.signed_coverage import producer as coverage
from research.signed_coverage import checker as coverage_checker
from research.signed_coverage import runtime as covered_runtime
from research.signed_reduction import checker as reduction_checker
from research.signed_predicates import semantics as native
from research.signed_context import session
from research.signed_context.io import freeze, load_json, save_json
from research.unified import v6, v7
from research.unified.checker import InvalidProof

ROOT = Path(__file__).resolve().parents[2]
TRUE = ['or', ['negative'], ['nonnegative']]
FALSE = ['and', ['negative'], ['nonnegative']]
POWER = ['and', ['positive'], ['popcount_eq', 1]]


def source(expr, typ='long', name='Demo'):
    return f'class {name} {{ public static boolean f({typ} x) {{ return {expr}; }} }}'


def selection(typ='long', name='Demo'):
    return request({'class': name, 'method': 'f'}, typ)


def target(goal=POWER, typ='long', name='Demo'):
    return {'schema':'qkf-target-v2', 'kind':'signed_boolean_predicate',
            'source':{'entry':{'class':name,'method':'f'},'word_type':typ},'goal':deepcopy(goal)}


class ContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = source('x > 0 && (x & (x-1)) == 0')
        cls.sel = selection()
        cls.obs, _ = coverage.infer(cls.text, cls.sel)
        cls.ctx = session.load(cls.text, cls.sel, cls.obs)
        cls.positive, cls.proof = cls.ctx.prove(target())
        cls.negative, cls.badproof = cls.ctx.prove(target(FALSE))

    def test_one_parse_and_one_shared_rebuild_at_load(self):
        with mock.patch.object(reduction_checker, 'read', wraps=reduction_checker.read) as parser, \
             mock.patch.object(covered_runtime, 'rebuild_observations', wraps=covered_runtime.rebuild_observations) as rebuild:
            ctx = session.load(self.text, self.sel, self.obs)
            self.assertEqual((parser.call_count, rebuild.call_count), (1, 1))
            for goal in (POWER, FALSE, TRUE, ['negative']):
                r, p = ctx.prove(target(goal)); self.assertEqual(ctx.check(target(goal), p), r)
                ctx.explain(target(goal), p)
            self.assertEqual((parser.call_count, rebuild.call_count), (1, 1))

    def test_no_shared_work_after_load_positive_negative_explain(self):
        def forbidden(*a, **kw): raise AssertionError('shared reconstruction after load')
        with mock.patch.object(reduction_checker, 'read', side_effect=forbidden), \
             mock.patch.object(covered_runtime, 'rebuild_observations', side_effect=forbidden), \
             mock.patch.object(coverage_checker, 'rebuild', side_effect=forbidden), \
             mock.patch.object(native, 'initial', side_effect=forbidden), \
             mock.patch.object(native, 'cell', side_effect=forbidden):
            for goal in (POWER, FALSE, TRUE):
                r, p = self.ctx.prove(target(goal))
                self.assertEqual(self.ctx.check(target(goal), p), r)
                self.assertEqual(self.ctx.explain(target(goal), p)['result'], r)
            self.assertTrue(self.ctx.value(1,64))

    def test_exact_v6_positive_result_and_proof(self):
        self.assertEqual(v6.prove(self.text,target()), (self.positive,self.proof))
        self.assertEqual(v6.check(self.text,target(),self.proof), self.positive)

    def test_exact_v6_negative_result_and_proof(self):
        self.assertEqual(v6.prove(self.text,target(FALSE)), (self.negative,self.badproof))
        self.assertEqual(v6.check(self.text,target(FALSE),self.badproof),self.negative)

    def test_cold_new_entry_replays_existing_v6(self):
        self.assertEqual(v7.check(self.text,target(),self.proof),self.positive)
        self.assertEqual(session.check(self.text,target(FALSE),self.badproof),self.negative)

    def test_v7_produce_same_portable_envelope(self):
        self.assertEqual(v7.prove(self.text,target()),(self.positive,self.proof))

    def test_multiple_targets_same_interface(self):
        pairs=self.ctx.prove_many([target(g) for g in (POWER,FALSE,TRUE,['negative'])])
        self.assertEqual([r['status'] for r,p in pairs],['certified','refuted','refuted','refuted'])
        self.assertTrue(all(p['proof']['observations']==self.obs for r,p in pairs))

    def test_batch_presupplied_interface_loads_once(self):
        with mock.patch.object(covered_runtime,'load',wraps=covered_runtime.load) as ld:
            inspection,pairs=v7.batch(self.text,[target(),target(FALSE)],observations=self.obs)
            self.assertEqual(ld.call_count,1);self.assertEqual(len(pairs),2)
            self.assertFalse(inspection['target_checked'])

    def test_batch_builds_one_interface_not_one_per_target(self):
        with mock.patch.object(coverage,'infer',wraps=coverage.infer) as inf:
            _,pairs=v7.batch(self.text,[target(),target(FALSE)])
            self.assertEqual(inf.call_count,1);self.assertEqual(len(pairs),2)

    def test_wrong_target_entry(self):
        with self.assertRaises(ValueError):self.ctx.prove(target(name='Other'))
        with self.assertRaises(InvalidProof):self.ctx.check(target(name='Other'),self.proof)

    def test_wrong_word_type(self):
        with self.assertRaises(ValueError):self.ctx.prove(target(typ='int'))

    def test_mutated_source_rejected_cold(self):
        with self.assertRaises(InvalidProof):v7.check(self.text.replace('x > 0','x >= 0'),target(),self.proof)

    def test_source_only_not_target_certificate(self):
        with self.assertRaises(InvalidProof):self.ctx.check(target(),self.obs)
        with self.assertRaises(InvalidProof):v7.check(self.text,target(),self.obs)

    def test_changed_observation_not_cache_hit(self):
        p=deepcopy(self.proof);p['proof']['observations']['source_model']['edges'][0]['next']=0
        with self.assertRaises(InvalidProof):self.ctx.check(target(),p)
        with self.assertRaises(InvalidProof):v7.check(self.text,target(),p)

    def test_removed_guard_rejected_even_with_full_hash_update(self):
        text=source('x == 16');obs,_=coverage.infer(text,selection())
        edge=next(e for e in obs['source_model']['edges'] if e['proof']['retired_equalities'])
        edge['proof']['retired_equalities']=[]
        with self.assertRaises(ValueError):session.load(text,selection(),obs)

    def test_damaged_rows_rejected_load(self):
        obs=deepcopy(self.obs);obs['observations']['rows'][0]['supplied'][0][1] ^= 1
        with self.assertRaises(ValueError):session.load(self.text,self.sel,obs)

    def test_forged_closed_subset_rejected(self):
        p=deepcopy(self.proof);p['proof']['obligation']['states']=p['proof']['obligation']['states'][:1]
        with self.assertRaises(InvalidProof):self.ctx.check(target(),p)

    def test_changed_goal_rebinding_does_not_prove_it(self):
        from research.signed_coverage.targets import binding,prepare
        p=deepcopy(self.proof);t=target(FALSE);compiled,_=prepare(t)
        p['proof']['binding']=binding(compiled,self.ctx.describe()['runtime'])
        with self.assertRaises(InvalidProof):self.ctx.check(t,p)

    def test_saved_result_forgery(self):
        p=deepcopy(self.badproof);p['result']['status']='certified'
        with self.assertRaises(InvalidProof):self.ctx.check(target(FALSE),p)

    def test_context_constructor_cannot_accept_receipt(self):
        with self.assertRaises(ValueError):session.CheckedContext()
        with self.assertRaises(ValueError):session.CheckedContext(self.ctx.describe())

    def test_context_not_pickle_restorable(self):
        with self.assertRaises(TypeError):pickle.dumps(self.ctx)

    def test_immutable_fields(self):
        with self.assertRaises((FrozenInstanceError,AttributeError)):self.ctx._ir_json='{}'
        self.assertIsInstance(self.ctx._ir_json,str)
        self.assertIsInstance(self.ctx._observations_json,str)

    def test_caller_mutation_does_not_change_context(self):
        sel,obs=deepcopy(self.sel),deepcopy(self.obs)
        ctx=session.load(self.text,sel,obs)
        obs.clear();sel.clear()
        self.assertEqual(ctx.prove(target()),(self.positive,self.proof))

    def test_export_inspection_and_output_are_detached(self):
        self.ctx.export_source_proof().clear();self.ctx.describe()['runtime'].clear()
        r,p=self.ctx.prove(target());r.clear();p['proof']['observations'].clear()
        self.assertEqual(self.ctx.prove(target()),(self.positive,self.proof))

    def test_stream_forks(self):
        prefix=self.ctx.start().feed('1')
        self.assertTrue(prefix.feed('0').finish());self.assertFalse(prefix.feed('1').finish())
        with self.assertRaises(ValueError):self.ctx.start().finish()

    def test_product_budget_does_not_poison_session(self):
        r,p=self.ctx.prove(target(),limits={'max_target_states':1})
        self.assertIsNone(p);self.assertEqual(r['status'],'budget_exhausted')
        self.assertEqual(self.ctx.prove(target()),(self.positive,self.proof))

    def test_witness_budget_no_partial_proof(self):
        r,p=self.ctx.prove(target(FALSE),limits={'max_witness_bits':0})
        self.assertIsNone(p);self.assertEqual(r['status'],'budget_exhausted')

    def test_target_only_budgets_on_loaded_context(self):
        for limits in ({'max_states':64},{'max_target_states':True},{'max_witness_bits':4097}):
            with self.assertRaises(ValueError):self.ctx.prove(target(),limits=limits)

    def test_batch_target_validation_before_work(self):
        with mock.patch.object(coverage,'infer',side_effect=AssertionError('should not construct')):
            with self.assertRaises(ValueError):v7.batch(self.text,[target(),target(typ='int')])
        for ts in ([],[target()]*65,{}):
            with self.assertRaises(ValueError):self.ctx.prove_many(ts)

    def test_build_exhaustion_returns_no_context(self):
        ctx,r=session.build(self.text,self.sel,limits={'max_states':1})
        self.assertIsNone(ctx);self.assertEqual(r['status'],'budget_exhausted')

    def test_unsupported_body_not_skipped(self):
        ctx,r=session.build(source('(x << 1) == 0'),self.sel)
        self.assertIsNone(ctx);self.assertEqual(r['status'],'unsupported')

    def test_original_ir_bound_in_context(self):
        obs=deepcopy(self.obs);obs['source_model']['reduction']['original_ir']['formula']=['literal',True]
        with self.assertRaises(ValueError):session.load(self.text,self.sel,obs)

    def test_small_width_refutation_not_native_bug(self):
        text=source('x > 0 || (x == 2 && x < 0)');ctx,_=session.build(text,self.sel)
        r,p=ctx.prove(target(['positive']))
        self.assertEqual(r['inner']['target']['witness_width'],2)
        self.assertEqual(r['inner']['target']['native_width_witnesses'],[])
        self.assertEqual(v6.check(text,target(['positive']),p),r)

    def test_bad_prefix_not_final_witness(self):
        ctx,_=session.build(source('x<0'),self.sel)
        r,p=ctx.prove(target(FALSE))
        p['proof']['obligation']['word']=['1','0']
        with self.assertRaises(InvalidProof):ctx.check(target(FALSE),p)

    def test_int_negative_native_payload_matches_old(self):
        text=source('x<0','int');ctx,_=session.build(text,selection('int'))
        r,p=ctx.prove(target(FALSE,'int'));self.assertEqual(v6.check(text,target(FALSE,'int'),p),r)
        self.assertEqual(r['inner']['target']['java_width'],32)

    def test_positive_check_does_not_evaluate_whole_words(self):
        with mock.patch.object(session,'check_ir',side_effect=AssertionError('wrong branch')):
            self.assertEqual(self.ctx.check(target(),self.proof),self.positive)

    def test_tautology_and_large_coverage(self):
        for expr,count in [('x == 2147483648L || x != 2147483648L',2),('x == 2305843009213693952L',64)]:
            ctx,_=session.build(source(expr),self.sel)
            self.assertEqual(ctx.describe()['runtime']['classes'],count)
            r,p=ctx.prove(target(TRUE));self.assertEqual(v6.check(source(expr),target(TRUE),p),r)

    def test_fresh_guarded_checker_and_lazy_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);save_json(root/'proof.json',self.proof);save_json(root/'bad.json',self.badproof)
            (root/'source.java').write_text(self.text)
            script=r'''
import importlib.abc,json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self,name,path=None,target=None):
  if name in {'subprocess','z3','cvc5','pysmt','research.observations.run_package','research.unified.run','research.unified.v6','research.unified.v5','research.unified.v4'} or name.startswith(('research.graal','research.knownbits','research.inference')) or (name.startswith('research.') and name.rsplit('.',1)[-1].startswith('producer')):
   raise ImportError('unexpected import '+name)
sys.meta_path.insert(0,Guard())
from research.unified import v7
from research.signed_context.session import load,prepare
p=Path(sys.argv[2]);source=(p/'source.java').read_text()
t=lambda g:{'schema':'qkf-target-v2','kind':'signed_boolean_predicate','source':{'entry':{'class':'Demo','method':'f'},'word_type':'long'},'goal':g}
positive=t(['and',['positive'],['popcount_eq',1]]);negative=t(['and',['negative'],['nonnegative']])
proof=json.loads((p/'proof.json').read_text());bad=json.loads((p/'bad.json').read_text())
if v7.check(source,positive,proof)['status']!='certified':raise RuntimeError('positive replay')
ctx=load(source,prepare(positive)[1],proof['proof']['observations'])
if ctx.check(negative,bad)['status']!='refuted':raise RuntimeError('negative replay')
if ctx.explain(negative,bad)['result']['status']!='refuted':raise RuntimeError('explanation replay')
print('guarded replay passed')
'''
            for mode in ([],['-O']):
                done=subprocess.run([sys.executable,'-I','-B',*mode,'-c',script,str(ROOT),tmp],capture_output=True,text=True)
                self.assertEqual(done.returncode,0,done.stderr);self.assertIn('passed',done.stdout)

    def test_legacy_v5_concrete_proof_retains_identity(self):
        from research.unified import v5
        text=source('x>=0');t=target(['positive']);r,p=v5.prove(text,t)
        self.assertEqual(v7.check(text,t,p),r)

    def test_non_signed_proof_delegates(self):
        from research.unified import v3
        from research.unified.experiment import WORD_SOURCE, WORD_TARGET
        r,p=v3.prove(WORD_SOURCE,WORD_TARGET)
        self.assertEqual(r['status'],'certified')
        self.assertEqual(v7.prove(WORD_SOURCE,WORD_TARGET),(r,p))
        self.assertEqual(v7.check(WORD_SOURCE,WORD_TARGET,p),r)

    def test_json_rejects_duplicates_nonfinite_types(self):
        for value in ({1:2},(1,2),float('nan')):
            with self.assertRaises(ValueError):freeze(value)
        cycle=[];cycle.append(cycle)
        with self.assertRaises(ValueError):freeze(cycle)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json'
            for raw in ('{"a":1,"a":2}','{"a":NaN}'):
                p.write_text(raw)
                with self.assertRaises(ValueError):load_json(p)

    def test_cli_batch_and_exclusive_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'source.java').write_text(self.text)
            save_json(p/'targets.json',[target(),target(FALSE)])
            save_json(p/'obs.json',self.obs)
            args=[sys.executable,'-m','research.unified.v7','batch',str(p/'source.java'),
                  '--target',str(p/'targets.json'),'--proof',str(p/'out'),'--observations',str(p/'obs.json')]
            done=subprocess.run(args,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(done.returncode,1,done.stderr);self.assertEqual(json.loads(done.stdout)['proofs'],2)
            again=subprocess.run(args,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(again.returncode,64)
            for i,code in [(0,0),(1,1)]:
                checked=subprocess.run([sys.executable,'-O','-m','research.unified.v7','check',str(p/'source.java'),
                    '--target',str(p/'out'/f'target-{i:03d}.json'),'--proof',str(p/'out'/f'proof-{i:03d}.json')],
                    cwd=ROOT,capture_output=True,text=True)
                self.assertEqual(checked.returncode,code,checked.stderr)

    def test_cli_invalid_certificate_and_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'s.java').write_text(self.text);save_json(p/'t.json',target());save_json(p/'p.json',{})
            args=[sys.executable,'-m','research.unified.v7','check',str(p/'s.java'),'--target',str(p/'t.json'),'--proof',str(p/'p.json')]
            done=subprocess.run(args,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(done.returncode,3,done.stderr)
            save_json(p/'b.json',{'max_states':1});args[3]='prove';args[-1]=str(p/'absent.json')
            done=subprocess.run(args+['--budget',str(p/'b.json')],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(done.returncode,2,done.stderr);self.assertFalse((p/'absent.json').exists())

    def test_differential_many_sources_goals(self):
        import random
        rng=random.Random(3601)
        expressions=['x<0','x==4','x!=0','(x+1)==4','(x-1)==4','(x & 3)==0',
                     'x==4 || x<0','x<=0','x==4 || x!=4','x>0 && (x & (x-1))==0']
        goals=[TRUE,FALSE,POWER,['positive'],['negative'],['popcount_le',2]]
        for expr in expressions:
            text=source(expr);ctx,_=session.build(text,self.sel)
            for g in rng.sample(goals,3):
                t=target(g);r,p=ctx.prove(t)
                self.assertEqual(v6.check(text,t,p),r)

    def test_wide_supplied_negative_obligation(self):
        text=source('x<0');ctx,_=session.build(text,self.sel)
        r,p=ctx.prove(target(FALSE))
        obligation={'kind':'counterexample','word':['0']*4095+['1']}
        compiled=ctx._prepare(target(FALSE))
        p['proof']['obligation']=obligation
        p['result']=ctx._check_obligation(compiled,obligation)
        self.assertEqual(ctx.check(target(FALSE),p),v6.check(text,target(FALSE),p))
        self.assertEqual(p['result']['inner']['target']['witness_width'],4096)

    def test_explanation_is_detached_and_target_checked(self):
        output=self.ctx.explain(target(FALSE),self.badproof)
        self.assertTrue(output['result']['target_checked'])
        output['interface'].clear();output['obligation'].clear()
        self.assertEqual(self.ctx.check(target(FALSE),self.badproof),self.negative)

    def test_receipt_cannot_load_as_source_proof(self):
        with self.assertRaises(ValueError):session.load(self.text,self.sel,self.ctx.describe()['runtime'])

    def test_load_only_one_generic_observation_check(self):
        from research.observations import checker as generic
        with mock.patch.object(generic,'check',wraps=generic.check) as counted:
            ctx=session.load(self.text,self.sel,self.obs)
            for t,p in [(target(),self.proof),(target(FALSE),self.badproof)]:ctx.check(t,p)
            self.assertEqual(counted.call_count,1)


if __name__=='__main__':unittest.main()
