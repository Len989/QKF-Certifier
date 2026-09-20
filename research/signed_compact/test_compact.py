"""Representation attacks, semantic differential checks and fresh-process replay."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import pickle
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from research.observations.model import Model, MODEL_SCHEMA
from research.signed_context.experiment import cases
from research.signed_context.session import build
from research.signed_context.io import freeze
from research.signed_targets.common import prepare
from research.unified.checker import InvalidProof
from . import checker, dag, finite, producer

ROOT = Path(__file__).resolve().parents[2]


class DagTests(unittest.TestCase):
    def test_plain_roundtrip(self):
        x={'unicode':'абв','values':[None,False,True,0,1,-7,'0',[],{}]}
        self.assertEqual(dag.unpack(dag.pack(x)),x)
    def test_sharing_and_detached_values(self):
        x={'one':[{'a':list(range(40))}]*10,'two':[{'a':list(range(40))}]*10}
        p=dag.pack(x); y=dag.unpack(p);y['one'][0]['a'][0]=99
        self.assertEqual(y['two'][0]['a'][0],0)
        self.assertEqual(dag.unpack(p),x)
        self.assertLess(len(freeze(p)),len(freeze(x)))
    def test_boolean_integer_not_conflated(self):
        x=[True,1,False,0];p=dag.pack(x)
        self.assertEqual([type(v) for v in dag.unpack(p)],[bool,int,bool,int])
    def test_forward_and_cyclic_reference(self):
        for nodes in ([['l',[0]]],[['l',[1]],['l',[0]]]):
            with self.assertRaises(ValueError):dag.unpack({'schema':dag.SCHEMA,'root':0,'nodes':nodes})
    def test_invalid_ref_type(self):
        for ref in (True,1.0,-1,'0',None):
            with self.assertRaises(ValueError):dag.unpack({'schema':dag.SCHEMA,'root':1,'nodes':[['v',0],['l',[ref]]]})
    def test_unused_node(self):
        p=dag.pack([0]);p['nodes'].append(['v',2])
        with self.assertRaises(ValueError):dag.unpack(p)
    def test_duplicate_node(self):
        with self.assertRaises(ValueError):dag.unpack({'schema':dag.SCHEMA,'root':2,
            'nodes':[['v',0],['v',0],['l',[0,1]]]})
    def test_duplicate_or_unsorted_keys(self):
        for keys in ([['a',0],['a',0]],[['z',0],['a',0]]):
            with self.assertRaises(ValueError):dag.unpack({'schema':dag.SCHEMA,'root':1,'nodes':[['v',0],['d',keys]]})
    def test_no_float_or_code_objects(self):
        for x in (1.0,float('nan'),(0,),set(),lambda:None):
            with self.assertRaises((ValueError,TypeError)):dag.pack(x)
    def test_expansion_bomb_rejected_before_decode(self):
        nodes=[['v','a']]
        for i in range(1,32):nodes.append(['l',[i-1,i-1]])
        with self.assertRaisesRegex(ValueError,'expansion'):dag.unpack({'schema':dag.SCHEMA,'root':31,'nodes':nodes})
    def test_depth_budget(self):
        nodes=[['v',0]]+[['l',[i-1]] for i in range(1,132)]
        with self.assertRaisesRegex(ValueError,'depth'):dag.unpack({'schema':dag.SCHEMA,'root':131,'nodes':nodes})
    def test_shape_and_root(self):
        for p in ({}, {'schema':dag.SCHEMA,'root':False,'nodes':[['v',0]]},
                  {'schema':dag.SCHEMA,'root':0,'nodes':[['code','print(1)']]}):
            with self.assertRaises(ValueError):dag.unpack(p)


class CompactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _,cls.text,cls.targets=next(cases())
        cls.selection=prepare(cls.targets[0])[1]
        ctx,_=build(cls.text,cls.selection)
        cls.old=[p for r,p in ctx.prove_many(cls.targets)]
        cls.results,cls.packet=producer.pack_proofs(cls.text,cls.targets,cls.old)
        cls.logical=dag.unpack(cls.packet)

    def bad(self,fn):
        x=deepcopy(self.logical);fn(x)
        with self.assertRaises(InvalidProof):checker.check(self.text,self.targets,dag.pack(x))

    def test_roundtrip_status_and_scope(self):
        r=checker.check(self.text,self.targets,self.packet)
        self.assertEqual(r,self.results);self.assertEqual([x['status'] for x in r],[p['result']['status'] for p in self.old])
        self.assertTrue(all(x['target_checked'] and not x['lean_checked'] for x in r))
    def test_no_pair_witness_storage(self):
        self.assertNotIn('separators',self.logical['source']['observations'])
        self.assertEqual(checker.load(self.text,self.targets,self.packet).describe()['stored_pair_witnesses'],0)
    def test_semantic_check_does_not_materialize_pairs(self):
        with patch.object(finite,'separator',side_effect=AssertionError('all-pair expansion')):
            self.assertEqual(checker.check(self.text,self.targets,self.packet),self.results)
    def test_all_on_demand_pairs_match_old(self):
        ctx=checker.load(self.text,self.targets,self.packet)
        old=self.old[0]['proof']['observations']['observations']['separators']
        for w in old:self.assertEqual(ctx.explain_pair(w['left'],w['right'])['witness'],w)
    def test_pair_reuses_checked_source(self):
        ctx=checker.load(self.text,self.targets,self.packet)
        with patch.object(checker,'rebuild',side_effect=AssertionError('rebuild')),patch.object(finite,'check',side_effect=AssertionError('atomic')):
            self.assertEqual(ctx.explain_pair(0,1)['status'],'separation_verified')
            self.assertEqual(ctx.check_obligation(self.targets[0],self.old[0]['proof']['obligation']),self.results[0])
    def test_invalid_pairs(self):
        ctx=checker.load(self.text,self.targets,self.packet)
        for pair in [(0,0),(1,0),(-1,1),(False,1),(0,999)]:
            with self.assertRaises(ValueError):ctx.explain_pair(*pair)
    def test_export_all_targets_old_checker(self):
        from research.unified.v6 import check
        for i,t in enumerate(self.targets):
            p=checker.export_legacy(self.text,self.targets,self.packet,i)
            self.assertEqual(check(self.text,t,p),self.old[i]['result'])
            self.assertEqual(p,self.old[i])
    def test_old_checker_rejects_compact_schema(self):
        from research.unified.v6 import check
        with self.assertRaises(Exception):check(self.text,self.targets[0],self.packet)
    def test_invalid_old_witness_not_dropped_before_validation(self):
        ps=deepcopy(self.old);ps[0]['proof']['observations']['observations']['separators']=[]
        with self.assertRaises(Exception):producer.pack_proofs(self.text,self.targets,ps)
    def test_input_source_change(self):
        with self.assertRaises(InvalidProof):checker.check(self.text+' ',self.targets,self.packet)
    def test_target_change(self):
        ts=deepcopy(self.targets);ts[0]['goal']=['negative']
        with self.assertRaises(InvalidProof):checker.check(self.text,ts,self.packet)
    def test_rehashed_goal_does_not_pass_product(self):
        x=deepcopy(self.logical);ts=deepcopy(self.targets);ts[0]['goal']=['negative'];x['items'][0]['target']=ts[0]
        with self.assertRaises(InvalidProof):checker.check(self.text,ts,dag.pack(x))
    def test_target_list_order_and_coverage(self):
        for ts in (self.targets[:-1],list(reversed(self.targets)),[]):
            with self.assertRaises(InvalidProof):checker.check(self.text,ts,self.packet)
    def test_changed_selection(self):self.bad(lambda x:x['selection'].__setitem__('word_type','int'))
    def test_fake_source_receipt(self):self.bad(lambda x:x.__setitem__('source',{'status':'source_runtime_verified'}))
    def test_source_only_cannot_replace_target(self):self.bad(lambda x:x['items'][0].__setitem__('obligation',{'status':'source_model_verified'}))
    def test_missing_product_state(self):self.bad(lambda x:x['items'][0]['obligation']['states'].pop())
    def test_final_width_witness(self):self.bad(lambda x:x['items'][1]['obligation'].__setitem__('word',[]))
    def test_original_ir_tampering(self):
        self.bad(lambda x:x['source']['source_model']['reduction']['original_ir'].__setitem__('formula',['const',True]))
    def test_coverage_branch_omission(self):self.bad(lambda x:x['source']['source_model']['edges'].pop())
    def test_coverage_guard_corruption(self):
        self.bad(lambda x:x['source']['source_model']['edges'][0]['proof'].__setitem__('retired_equalities',[999]))
    def test_wrong_question_mask(self):self.bad(lambda x:x['source']['observations']['predicates'][0].__setitem__('mask',0))
    def test_cyclic_question_origin(self):
        def f(x):
            ps=x['source']['observations']['predicates'];i=next(i for i,p in enumerate(ps) if p['kind']=='pullback');ps[i]['parent']=i
        self.bad(f)
    def test_false_row_label_and_atom(self):
        self.bad(lambda x:x['source']['observations']['rows'][0]['supplied'][0].__setitem__(1,1))
    def test_wrong_cell(self):self.bad(lambda x:x['source']['observations']['cells'][0].__setitem__('next',0))
    def test_false_kernel(self):self.bad(lambda x:x['source']['observations']['blocks'].pop())
    def test_unknown_separation_policy(self):self.bad(lambda x:x['source']['observations'].__setitem__('separation','trust-me'))
    def test_unknown_item_field(self):self.bad(lambda x:x['items'][0].__setitem__('cached_success',True))
    def test_deep_detachment_and_immutability(self):
        packet=deepcopy(self.packet);ctx=checker.load(self.text,self.targets,packet);packet['nodes'].clear()
        r=ctx.results();r[0]['status']='fake';d=ctx.describe();d['source']['identity'].clear()
        self.assertEqual(ctx.results(),self.results)
        with self.assertRaises(FrozenInstanceError):ctx._model_json='fake'
        with self.assertRaises(ValueError):checker.VerifiedBundle()
        with self.assertRaises(TypeError):pickle.dumps(ctx)
    def test_stream_forks(self):
        ctx=checker.load(self.text,self.targets,self.packet)
        self.assertEqual(ctx.value(8,64),True)
        cur=ctx.start();self.assertIsNotNone(cur)
    def test_explicit_export_not_called_by_load(self):
        with patch.object(checker,'export_legacy',side_effect=AssertionError('export')):
            checker.load(self.text,self.targets,self.packet)
    def test_no_partial_bundle_on_budget(self):
        results,p=producer.prove_many(self.text,self.targets,budgets={'max_states':1})
        self.assertIsNone(p);self.assertTrue(all(r['status']=='budget_exhausted' for r in results))
    def test_larger_family_sizes_and_exports(self):
        for k in (4,8,30):
            text=f'class Demo {{ public static boolean f(long x) {{ return x == {1<<k}L; }} }}'
            ts=[self.targets[3]];rs,p=producer.prove_many(text,ts)
            old=checker.export_legacy(text,ts,p)
            self.assertLess(len(freeze(p)),len(freeze(old)))
            self.assertEqual(rs[0]['status'],'refuted')
    def test_fresh_replay_blocks_producers_and_pair_expansion(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'data.json').write_text(json.dumps([self.text,self.targets,self.packet,self.results]))
            code='''import sys,importlib.abc,json
sys.path.insert(0,sys.argv[1])
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self,n,path=None,target=None):
  if n in {'subprocess','platform','z3','pysmt','research.unified.v6','research.unified.v7'} or (n.startswith('research.') and n.rsplit('.',1)[-1].startswith('producer')):raise ImportError(n)
sys.meta_path.insert(0,Guard())
from research.signed_compact import checker,finite
source,targets,packet,expected=json.load(open(sys.argv[2]))
def fail(*a,**k):raise RuntimeError('pair materialization forbidden')
finite.separator=fail
def profile(frame,event,arg):
 if event=='call' and frame.f_globals.get('__name__')=='research.observations.checker':fail()
sys.setprofile(profile)
if checker.check(source,targets,packet)!=expected:raise RuntimeError('replay mismatch')
'''
            for opt in ([],['-O']):
                r=subprocess.run([sys.executable,*opt,'-I','-S','-B','-c',code,str(ROOT),str(p/'data.json')],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stderr)
    def test_cli_check_pair_export_exclusive(self):
        from .cli import main
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'s.java').write_text(self.text);(p/'t.json').write_text(json.dumps(self.targets));(p/'p.json').write_text(json.dumps(self.packet))
            tail=[str(p/'s.java'),'--targets',str(p/'t.json'),'--proof',str(p/'p.json')]
            self.assertEqual(main(['check',*tail]),1)
            self.assertEqual(main(['pair',*tail,'--left','0','--right','1']),0)
            self.assertEqual(main(['export',*tail,'--out',str(p/'e.json')]),0)
            self.assertEqual(main(['export',*tail,'--out',str(p/'e.json')]),64)
            (p/'p.json').write_text('{"a":1,"a":2}')
            self.assertEqual(main(['check',*tail]),3)


class FiniteTests(unittest.TestCase):
    def test_seeded_models_and_all_separators(self):
        from research.observations.producer import synthesize
        from research.observations.checker import check as old_check
        rng=random.Random(3700)
        for _ in range(80):
            n=rng.randrange(1,9);names=[str(i) for i in range(n)]
            m=Model({'schema':MODEL_SCHEMA,'states':names,'initial':'0','alphabet':['0','1'],
                     'outputs':['a','b'],'terminal':{s:rng.choice(['no','yes']) for s in names},'binding':{},
                     'steps':[{'state':s,'symbol':b,'output':rng.choice(['a','b']),'next':rng.choice(names)} for s in names for b in ['0','1']]})
            old=synthesize(m.data,row_encoding='atomic')['certificate'];oc=old_check(m.data,old)
            cp=deepcopy(old);cp.pop('separators');cp['schema']=finite.SCHEMA;cp['separation']=finite.POLICY
            nc=finite.check(m.data,cp);self.assertEqual(nc['minimality'],oc['minimality']);self.assertEqual(nc['classes'],oc['classes'])
            for w in old['separators']:self.assertEqual(finite.separator(m,cp,w['left'],w['right'])[0],w)
    def test_overrefined_identical_behavior_rejected(self):
        from research.observations.producer import synthesize
        m=Model({'schema':MODEL_SCHEMA,'states':['a','b'],'initial':'a','alphabet':['0'],'outputs':['_'],
            'terminal':{'a':'same','b':'same'},'binding':{},'steps':[{'state':s,'symbol':'0','output':'_','next':'b'} for s in ['a','b']]})
        cp=synthesize(m.data,row_encoding='atomic')['certificate'];cp.pop('separators');cp['schema']=finite.SCHEMA;cp['separation']=finite.POLICY
        finite.check(m.data,cp);cp['blocks']=[['a'],['b']]
        with self.assertRaises(ValueError):finite.check(m.data,cp)

if __name__=='__main__':unittest.main()
