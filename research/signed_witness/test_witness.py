"""Concrete negative proof, no-factor isolation, fallback and hostile inputs."""
from copy import deepcopy
import contextlib
import io
import itertools
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from research.observations.model import digest
from research.signed_predicates import semantics
from research.signed_predicates.frontend import read_source, target_value
from research.unified import v4, v5
from research.unified.checker import InvalidProof
from research.wordexpr.frontend import Unsupported
from . import checker, producer
from .common import ENGINE, MAX_WIDTH, binding, budgets, prepare

ROOT = Path(__file__).resolve().parents[2]
FALSE = ['and', ['negative'], ['nonnegative']]
TRUE = ['or', ['negative'], ['nonnegative']]
POWER = ['and', ['positive'], ['popcount_eq', 1]]


def source(expression, typ='long', prefix='', name='Demo', method='f'):
    return f'class {name} {{ public static boolean {method}({typ} x) {{ {prefix}return {expression}; }} }}'


def target(formula=FALSE, typ='long', name='Demo', method='f'):
    return {'schema':'qkf-target-v2','kind':'signed_boolean_predicate',
            'source':{'entry':{'class':name,'method':method},'word_type':typ}, 'goal':deepcopy(formula)}


class WitnessTests(unittest.TestCase):
    def setUp(self):
        self.text, self.goal = source('x == 2147483648L'), target()
        self.cert, self.result = producer.from_raw(self.text, self.goal, 0, 1)

    def reject(self, cert):
        with self.assertRaises(ValueError): checker.check(self.text, self.goal, cert)

    def test_exact_pr32_source_and_target(self):
        entries = json.loads((ROOT/'research/acceptance/REGISTERED_CASES.json').read_text())
        if type(entries) is dict: entries = entries['cases']
        entry = next(e for e in entries if e['id']=='delayed_31')
        import hashlib
        self.assertEqual(hashlib.sha256(self.text.encode()).hexdigest(), entry['source_sha256'])
        self.assertEqual(digest(self.goal), entry['target_sha256'])
        c, r, report = producer.probe(self.text, self.goal)
        self.assertEqual(c, self.cert); self.assertEqual(r, self.result)
        self.assertEqual(report['evaluations'], 1)
        self.assertEqual(r['witness_width'], 1); self.assertEqual(r['input'], 0)

    def test_no_residual_or_model_calls(self):
        import research.wordexpr.semantics as words
        with contextlib.ExitStack() as stack:
            for module, name in ((semantics,'initial'), (semantics,'cell'), (semantics,'terminal'),
                                 (semantics,'model'), (words,'initial'), (words,'cell')):
                stack.enter_context(mock.patch.object(module, name, side_effect=AssertionError('no factor')))
            r, p, d = v5.prove_with_diagnostics(self.text, self.goal,
                                               budgets={'fallback':{'max_states':1}})
            self.assertEqual(r['status'], 'refuted'); self.assertFalse(d['fallback_used'])
            self.assertEqual(v5.check(self.text, self.goal, p), r)

    def test_old_route_still_exhausts(self):
        r, p = v4.prove(self.text, self.goal)
        self.assertEqual(r['status'], 'budget_exhausted'); self.assertIsNone(p)

    def test_small_width_does_not_lift_to_native(self):
        c, r, _ = producer.probe(source('x > 0 || (x == 2 && x < 0)'), target(['positive']))
        self.assertEqual(r['witness_width'], 2)
        self.assertFalse(r['witness_at_native_width']); self.assertFalse(r['native_execution_checked'])
        self.assertNotIn('native_width_witnesses', r)

    def test_supplied_native_word_and_int_overload(self):
        for typ, width in [('int',32),('long',64)]:
            c, r = producer.from_raw(source('x != 0 && (x & (x-1))==0',typ),
                                     target(POWER,typ),1<<(width-1),width)
            self.assertTrue(r['witness_at_native_width'])
            self.assertFalse(r['native_execution_checked'])
            self.assertEqual(r['signed_input'], -(1<<(width-1)))

    def test_final_width_not_bad_prefix(self):
        # At width one raw=1 is negative; appended zero changes it to positive.
        text, goal = source('x<0'), target()
        producer.from_raw(text, goal, 1, 1)
        with self.assertRaises(ValueError): producer.from_raw(text, goal, 1, 2)

    def test_empty_and_invalid_width(self):
        for width in (0,-1,4097,True,1.0,'1',None):
            with self.assertRaises(ValueError): producer.from_raw(self.text,self.goal,0,width)

    def test_raw_must_fit_no_modular_coercion(self):
        for raw in (-1,2,True,False,0.0,'0',None):
            with self.assertRaises(ValueError): producer.from_raw(self.text,self.goal,raw,1)

    def test_supplied_wide_word(self):
        c, r = producer.from_raw(source('true'), target(), (1<<4096)-1, 4096)
        self.assertEqual(checker.check(source('true'), target(), c), r)
        self.assertEqual(r['signed_input'], -1)

    def test_not_a_success_or_interface_theorem(self):
        r = self.result
        self.assertEqual(r['status'], 'refuted'); self.assertTrue(r['target_checked'])
        self.assertFalse(r['source_interface_verified']); self.assertFalse(r['all_positive_widths'])
        self.assertTrue(r['refutes_all_positive_widths']); self.assertFalse(r['lean_checked'])
        self.assertFalse(r['minimum_width_checked'])

    def test_unknown_or_missing_certificate_fields(self):
        for key in self.cert:
            c=deepcopy(self.cert); del c[key]; self.reject(c)
        self.reject({**self.cert,'observations':{}})
        self.reject({**self.cert,'schema':'qkf-signed-row-target-v1'})

    def test_witness_fields_and_types(self):
        for key in self.cert['witness']:
            c=deepcopy(self.cert); del c['witness'][key]; self.reject(c)
        for key,value in [('raw',False),('width',True),('source_result',1),('target_result',0),
                          ('word',[0]),('word','0'),('word',['00']),('word',[]),('raw',-1)]:
            c=deepcopy(self.cert); c['witness'][key]=value; self.reject(c)

    def test_word_raw_width_agreement(self):
        for key,value in [('raw',1),('word',['1']),('width',2)]:
            c=deepcopy(self.cert); c['witness'][key]=value; self.reject(c)

    def test_false_outputs_are_recomputed(self):
        c=deepcopy(self.cert); c['witness']['source_result']=False; self.reject(c)
        c=deepcopy(self.cert); c['witness']['target_result']=True; self.reject(c)

    def test_each_binding_is_checked(self):
        for key in self.cert['binding']:
            c=deepcopy(self.cert); c['binding'][key]='altered'; self.reject(c)

    def test_source_and_overload_substitution(self):
        for text,goal in [(self.text+'\n',self.goal),(source('false'),self.goal),
                          (self.text,target(typ='int')),(self.text,target(name='Other'))]:
            with self.assertRaises((ValueError,Unsupported)): checker.check(text,goal,self.cert)

    def test_rehashed_source_cannot_fake_mismatch(self):
        text=source('false'); c=deepcopy(self.cert)
        compiled,ir=prepare(text,self.goal); c['binding']=binding(compiled,ir)
        c['witness']['source_result']=False
        with self.assertRaises(ValueError): checker.check(text,self.goal,c)

    def test_rehashed_goal_cannot_fake_mismatch(self):
        goal=target(TRUE); c=deepcopy(self.cert)
        compiled,ir=prepare(self.text,goal); c['binding']=binding(compiled,ir)
        c['witness']['target_result']=True
        with self.assertRaises(ValueError): checker.check(self.text,goal,c)

    def test_rehashed_ir_binding_not_enough(self):
        c=deepcopy(self.cert); compiled,ir=prepare(self.text,self.goal)
        ir['formula']=['literal',False]; c['binding']=binding(compiled,ir); self.reject(c)

    def test_saved_unified_result_cannot_be_forged(self):
        r,p=v5.witness(self.text,self.goal,0,1)
        for key,value in [('status','certified'),('all_positive_widths',True),('engine','old')]:
            q=deepcopy(p);q['result'][key]=value
            with self.assertRaises(InvalidProof): v5.check(self.text,self.goal,q)

    def test_positive_package_not_concrete_proof(self):
        from research.signed_reduction.bridge import infer
        from research.signed_bridge.model import request
        text=source('true'); c,_=infer(text,request({'class':'Demo','method':'f'},'long'))
        with self.assertRaises(InvalidProof): v5.check(text,target(TRUE),c)
        r,p=v5.witness(self.text,self.goal,0,1)
        with self.assertRaises(InvalidProof): v4.check(self.text,self.goal,p)

    def test_no_witness_is_not_certified(self):
        c,r,d=producer.probe(source('x>0'),target(['positive']))
        self.assertIsNone(c);self.assertEqual(r['status'],'not_refuted')
        self.assertFalse(r['target_checked']);self.assertEqual(d['evaluations'],510)
        self.assertEqual(d['completed_widths'],list(range(1,9)))
        self.assertFalse(d['is_certificate'])

    def test_candidate_limit_exact_boundary(self):
        text,goal=source('x<0'),target(['negative'])
        c,r,d=producer.probe(text,goal,limits={'max_width':2,'max_evaluations':2})
        self.assertIsNone(c);self.assertEqual(r['status'],'budget_exhausted')
        self.assertEqual(d['completed_widths'],[1]);self.assertEqual(d['next_candidate'],{'width':2,'raw':0})
        c,r,d=producer.probe(text,goal,limits={'max_width':1,'max_evaluations':2})
        self.assertEqual(r['status'],'not_refuted')

    def test_zero_search_limits(self):
        for limits,status in [({'max_width':0},'not_refuted'),({'max_evaluations':0},'budget_exhausted')]:
            c,r,d=producer.probe(self.text,self.goal,limits=limits)
            self.assertIsNone(c);self.assertEqual(r['status'],status);self.assertEqual(d['evaluations'],0)

    def test_bad_search_budgets(self):
        for value in ({'unknown':1},{'max_width':21},{'max_width':True},{'max_evaluations':-1},
                      {'max_evaluations':1_000_001},[],{'max_width':1.0}):
            with self.assertRaises(ValueError): budgets(value)

    def test_true_fallback_matches_old_proof_exactly(self):
        text,goal=source('x>0 && (x & (x-1))==0'),target(POWER)
        r,p,d=v5.prove_with_diagnostics(text,goal)
        old_r,old_p=v4.prove(text,goal)
        self.assertEqual((r,p),(old_r,old_p));self.assertTrue(d['fallback_used'])
        self.assertEqual(v5.check(text,goal,p),r)
        self.assertEqual(v5.explain(text,goal,p),v4.explain(text,goal,p))

    def test_unseen_later_mismatch_reaches_fallback(self):
        text,goal=source('x == 256 && x > 0'),target()
        c,r,d=producer.probe(text,goal)
        self.assertIsNone(c);self.assertEqual(r['status'],'not_refuted')
        r,p,d=v5.prove_with_diagnostics(text,goal)
        self.assertTrue(d['fallback_used']);self.assertEqual(r['status'],'refuted')
        self.assertEqual(r['inner']['target']['witness_width'],10)
        self.assertNotEqual(r['engine'],ENGINE)

    def test_budget_failure_also_uses_fallback(self):
        r,p,d=v5.prove_with_diagnostics(source('x<0'),target(['negative']),
                         budgets={'search':{'max_evaluations':0}})
        self.assertEqual(r['status'],'certified');self.assertTrue(d['fallback_used'])
        self.assertEqual(d['precheck']['outcome'],'budget_exhausted')

    def test_no_witness_plus_incomplete_factor_is_unresolved(self):
        text=source('x == 2147483648L || x != 2147483648L')
        r,p,d=v5.prove_with_diagnostics(text,target(TRUE))
        self.assertIsNone(p);self.assertEqual(r['status'],'budget_exhausted')
        self.assertTrue(d['fallback_used']);self.assertEqual(d['precheck']['outcome'],'not_refuted')

    def test_search_options_cannot_weaken_the_goal(self):
        for value in ({'target':FALSE},{'search':{'goal':FALSE}},{'fallback':{'max_states':True}}):
            with self.assertRaises(ValueError):v5.prove(self.text,self.goal,budgets=value)

    def test_unsupported_even_in_dead_code(self):
        for prefix in ('long unused=x >> 1; ','long unused=x / 2; ','long unused=helper(x); '):
            c,r,d=producer.probe(source('true',prefix=prefix),target())
            self.assertIsNone(c);self.assertEqual(r['status'],'unsupported')
            self.assertEqual(d['evaluations'],0)
            with mock.patch.object(v4,'prove',side_effect=AssertionError('unsupported cannot fall back')):
                r,p,d=v5.prove_with_diagnostics(source('true',prefix=prefix),target())
                self.assertEqual(r['status'],'unsupported')

    def test_target_language_unchanged(self):
        for g in (['popcount_eq',4],['literal',False],['positive',1]):
            with self.assertRaises(ValueError):producer.search(self.text,target(g))

    def test_names_supply_no_semantics(self):
        for name,method in [('X','isPowerOfTwo'),('TotallyDifferent','f')]:
            text=source('true',name=name,method=method);goal=target(name=name,method=method)
            c,r=producer.search(text,goal);self.assertEqual(r['status'],'refuted')

    def test_independent_raw_goal_evaluation(self):
        goals=[(['positive'],lambda x,w:0<x<(1<<(w-1))),
               (['negative'],lambda x,w: bool(x & (1<<(w-1)))),
               (['popcount_eq',2],lambda x,w:bin(x).count('1')==2),
               (['popcount_le',3],lambda x,w:bin(x).count('1')<=3)]
        for (g,f), width in itertools.product(goals,range(1,7)):
            for raw in range(1<<width):
                text=source('false' if f(raw,width) else 'true')
                c,r=producer.from_raw(text,target(g),raw,width)
                self.assertEqual(r['expected'],f(raw,width))

    def test_seeded_expressions(self):
        rng=random.Random(34001)
        expressions=('(x & (x-1))==0','(x+3)<0','x==16','x>0','(x^7)!=0')
        for _ in range(48):
            expression=rng.choice(expressions);typ=rng.choice(('int','long'))
            width=rng.randrange(1,10);raw=rng.randrange(1<<width)
            text=source(expression,typ);ir=read_source(text,{'class':'Demo','method':'f'},typ)
            value=semantics.evaluate(ir,raw,width)
            goal=target(FALSE if value else TRUE,typ)
            c,r=producer.from_raw(text,goal,raw,width)
            self.assertEqual(r['output'],value);self.assertNotEqual(r['output'],r['expected'])

    def test_old_v1_v2_v3_dispatch(self):
        from research.unified.experiment import WORD_SOURCE,WORD_TARGET
        from research.unified.v3 import prove as old_v3
        text,goal=source('x>0 && (x & (x-1))==0'),target(POWER)
        for s,g in [(text,goal),(WORD_SOURCE,WORD_TARGET)]:
            r,p=old_v3(s,g)
            self.assertEqual(v5.check(s,g,p),r)
        r,p,d=v5.prove_with_diagnostics(WORD_SOURCE,WORD_TARGET)
        self.assertEqual(d['precheck']['outcome'],'not_applicable')
        self.assertEqual(v5.check(WORD_SOURCE,WORD_TARGET,p),r)

    def test_fresh_factor_free_replay(self):
        r,p=v5.witness(self.text,self.goal,0,1)
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'input.json';path.write_text(json.dumps([self.text,self.goal,p]))
            script='''
import importlib.abc,json,sys
sys.path.insert(0,sys.argv[1])
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  banned=('research.signed_bridge','research.signed_reduction','research.signed_observations',
          'research.signed_runtime','research.signed_targets','research.inference','research.unified.v4')
  if fullname in {'subprocess','z3','pysmt'} or fullname.endswith('.producer') or any(fullname==p or fullname.startswith(p+'.') for p in banned):
   raise ImportError('blocked '+fullname)
sys.meta_path.insert(0,Block())
from research.unified.v5 import check,explain
s,t,p=json.load(open(sys.argv[2]));r=check(s,t,p)
if r['status']!='refuted' or explain(s,t,p)['result']!=r: raise ValueError('replay')
print(json.dumps(r,sort_keys=True))
'''
            for flags in ([],['-O']):
                done=subprocess.run([sys.executable,'-I','-B',*flags,'-c',script,str(ROOT),str(path)],
                                    capture_output=True,text=True,check=True)
                self.assertEqual(json.loads(done.stdout),r)

    def cli(self,argv):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):code=v5.main(argv)
        return code,json.loads(out.getvalue())

    def test_cli_prove_check_explain_and_exclusive_files(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);s=d/'s.java';g=d/'g.json';p=d/'p.json';report=d/'report.json'
            s.write_text(self.text);g.write_text(json.dumps(self.goal))
            args=[str(s),'--target',str(g),'--proof',str(p)]
            code,r=self.cli(['prove',*args,'--diagnostics',str(report)])
            self.assertEqual(code,1);self.assertTrue(p.exists());self.assertTrue(report.exists())
            self.assertEqual(self.cli(['check',*args]),(1,r))
            self.assertEqual(self.cli(['explain',*args])[1]['result'],r)
            before=p.read_bytes();self.assertEqual(self.cli(['prove',*args])[0],64)
            self.assertEqual(p.read_bytes(),before)

    def test_cli_search_unresolved_has_no_proof(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);s=d/'s';g=d/'g';p=d/'p';s.write_text(source('true'));g.write_text(json.dumps(target(TRUE)))
            code,r=self.cli(['search',str(s),'--target',str(g),'--proof',str(p)])
            self.assertEqual(code,2);self.assertEqual(r['status'],'not_refuted');self.assertFalse(p.exists())

    def test_cli_supplied_witness(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);s=d/'s';g=d/'g';p=d/'p';s.write_text(self.text);g.write_text(json.dumps(self.goal))
            args=[str(s),'--target',str(g),'--proof',str(p)]
            self.assertEqual(self.cli(['witness',*args,'--raw','0','--width','1'])[0],1)
            self.assertEqual(self.cli(['check',*args,'--width','1'])[0],64)

    def test_cli_malformed_and_forged_json(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);s=d/'s';g=d/'g';p=d/'p';s.write_text(self.text);g.write_text(json.dumps(self.goal))
            for value in ('{"schema":"a","schema":"b"}','{"value":NaN}','{}'):
                p.write_text(value)
                self.assertEqual(self.cli(['check',str(s),'--target',str(g),'--proof',str(p)])[0],3)

    def test_snapshot_not_affected_by_caller_mutation(self):
        goal=deepcopy(self.goal);r,p=v5.witness(self.text,goal,0,1);saved=deepcopy(p)
        goal['goal']=TRUE
        self.assertEqual(p,saved);self.assertEqual(v5.check(self.text,self.goal,p),r)


if __name__=='__main__': unittest.main()
