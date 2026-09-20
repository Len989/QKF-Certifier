"""Local coverage, omission guards, source binding and explicit target integration."""
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
from research.signed_bridge.model import request, word_value
from research.signed_predicates import semantics as native
from research.signed_predicates.frontend import read_source
from research.wordexpr.frontend import Unsupported
from research.signed_reduction.rules import compact
from research.unified import v4, v5, v6
from research.unified.checker import InvalidProof
from . import local, producer, checker, runtime, targets, cli

ROOT = Path(__file__).resolve().parents[2]
FALSE = ['and', ['negative'], ['nonnegative']]
TRUE = ['or', ['negative'], ['nonnegative']]
POWER = ['and', ['positive'], ['popcount_eq', 1]]


def source(expr, typ='long', prefix='', name='Demo', method='f'):
    return f'class {name} {{ public static boolean {method}({typ} x) {{ {prefix}return {expr}; }} }}'


def selection(typ='long', name='Demo', method='f'):
    return request({'class': name, 'method': method}, typ)


def target(goal=FALSE, typ='long', name='Demo', method='f'):
    return {'schema':'qkf-target-v2','kind':'signed_boolean_predicate',
            'source':{'entry':{'class':name,'method':method},'word_type':typ}, 'goal':deepcopy(goal)}


class CoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = source('x == 16')
        cls.sel = selection()
        cls.cert, cls.checked = producer.infer(cls.text, cls.sel)

    def reject(self, cert):
        with self.assertRaises(ValueError): checker.check_observations(self.text, self.sel, cert)

    def test_exact_pr32_registration_and_34_states(self):
        import hashlib
        entries=json.loads((ROOT/'research/acceptance/REGISTERED_CASES.json').read_text())
        for name,expr,states in [('delayed_31','x == 2147483648L',34),
                                 ('tautology_31','x == 2147483648L || x != 2147483648L',2)]:
            text=source(expr); entry=next(e for e in entries if e['id']==name)
            self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),entry['source_sha256'])
            c,r=producer.infer(text,self.sel)
            self.assertEqual(r['coverage']['covered_states'],states)
            self.assertEqual(r['coverage']['original_states_enumerated'],0)
            self.assertEqual(checker.check_observations(text,self.sel,c),r)

    def test_nontrivial_positive_before_literal_expansion(self):
        text=source('(x == 2147483648L) && ((x & 1) == 1)')
        result,proof=v6.prove(text,target())
        self.assertEqual(result['status'],'certified')
        self.assertEqual(result['inner']['runtime']['coverage']['covered_states'],2)
        self.assertTrue(result['target_checked']);self.assertFalse(result['lean_checked'])

    def test_old_full_constructors_forbidden(self):
        import research.signed_bridge.producer as old
        import research.signed_reduction.bridge as reduced
        import research.signed_observations.producer as obs
        with (mock.patch.object(old,'derive',side_effect=AssertionError('full carrier')),
             mock.patch.object(reduced,'build',side_effect=AssertionError('full reduced carrier')),
             mock.patch.object(obs,'derive',side_effect=AssertionError('old observation route')),
             mock.patch.object(native,'model',side_effect=AssertionError('full carrier'))):
            c,r=producer.infer(source('x == 2147483648L'),self.sel)
            self.assertEqual(r['classes'],34)
            checker.check_observations(source('x == 2147483648L'),self.sel,c)

    def test_complement_and_absorption_do_not_require_target(self):
        for expr in ('x == 256 || x != 256','x == 256 && x != 256',
                     '(x<0) || ((x<0) && x==256)'):
            c,r=producer.infer(source(expr),self.sel)
            self.assertFalse(r['target_checked']);self.assertFalse(r['lean_checked'])
            self.assertLessEqual(r['coverage']['covered_states'],4)

    def test_large_constant_family_and_boundary(self):
        for k in (4,8,30,31,40,61):
            c,r=producer.infer(source(f'x == {1<<k}L'),self.sel)
            self.assertEqual(r['coverage']['covered_states'],k+3)
        c,r=producer.infer(source(f'x == {1<<62}L'),self.sel)
        self.assertIsNone(c);self.assertEqual(r['stage'],'guarded_coverage')
        self.assertEqual(r['attempt']['created_states'],64)

    def test_model_cap_is_not_raised(self):
        c,r=producer.infer(self.text,self.sel,max_states=6)
        self.assertIsNone(c);self.assertEqual(r['status'],'budget_exhausted')
        with self.assertRaises(ValueError): producer.infer(self.text,self.sel,max_states=65)

    def test_arithmetic_dependencies_retained_when_shared(self):
        text=source('(x == 16) || ((x + 1) < 0)')
        c,r=producer.infer(text,self.sel);run,_=runtime.load(text,self.sel,c)
        ir=read_source(text,self.sel['entry'],'long')
        for w in range(1,8):
            for x in range(1<<w): self.assertEqual(run.value(x,w),native.evaluate(ir,x,w))
        # Once equality is dead, sign can still change on each next bit.
        self.assertGreater(r['classes'],2)

    def test_false_signed_atom_is_not_absorbing(self):
        c,_=producer.infer(source('x<0'),self.sel)
        self.assertTrue(all(not e['proof']['retired_equalities'] for e in c['source_model']['edges']))
        run,_=runtime.load(source('x<0'),self.sel,c)
        self.assertTrue(run.run('1').finish());self.assertFalse(run.run('10').finish())

    def test_exhaustive_small_sources(self):
        exprs=['x==0','x==4','x!=4','x>0','x<=0','(x+1)==3',
               '(x-1)==0','(-x)==2','(~x)==2','(x&3)==2','(x|1)==3',
               '(x^3)==2','x>0 && (x&(x-1))==0','(x==4)||(x<0)',
               '(x==4)^(x>0)','(x==4)&&((x&1)==1)']
        for typ,expr in itertools.product(('int','long'),exprs):
            text=source(expr,typ);sel=selection(typ);c,r=producer.infer(text,sel)
            self.assertIsNotNone(c,(expr,r));run,_=runtime.load(text,sel,c)
            ir=read_source(text,sel['entry'],typ)
            for w in range(1,7):
                for x in range(1<<w): self.assertEqual(run.value(x,w),native.evaluate(ir,x,w),(typ,expr,w,x))

    def test_seeded_formula_contexts(self):
        rng=random.Random(3501)
        atoms=['x==4','x!=8','x<0','x>0','(x+1)==3','(x&1)==1']
        for _ in range(32):
            a,b=rng.sample(atoms,2);op=rng.choice(['&&','||','^'])
            text=source(f'({a}) {op} ({b})');c,r=producer.infer(text,self.sel)
            self.assertIsNotNone(c,r);run,_=runtime.load(text,self.sel,c)
            ir=read_source(text,self.sel['entry'],'long')
            for w in (1,3,6):
                for x in range(1<<w): self.assertEqual(run.value(x,w),native.evaluate(ir,x,w))

    def test_differential_full_old_carriers(self):
        from research.signed_bridge.producer import derive
        for expr in ('x==4','x!=16','x>0 && (x&(x-1))==0','(x==4)||(x<0)'):
            text=source(expr);old,_=derive(text,self.sel);new,_=producer.infer(text,self.sel)
            from research.observations.model import Model
            m1=Model(old['model']);m2=Model(new['source_model']['model'])
            pairs={(m1.initial,m2.initial)};queue=list(pairs)
            for p,q in queue:
                self.assertEqual(m1.terminal[p],m2.terminal[q])
                for a in ('0','1'):
                    pair=(m1.step[p,a][1],m2.step[q,a][1])
                    if pair not in pairs:pairs.add(pair);queue.append(pair)

    def test_arbitrary_omitted_coordinate_completions(self):
        # Exhaustively vary omitted coordinates, not only reachable representatives.
        text=source('x==4');c,_=producer.infer(text,self.sel)
        _,ir,_,_=checker.rebuild(text,self.sel,c['source_model'])
        for state in c['source_model']['states']:
            sliced,proj,res=local.view(ir,state);n=len(ir['nodes']);m=len(sliced['nodes'])
            domains=[]
            for row in ir['nodes']:
                domains.append(range(row[1]+1) if row[0]=='const' else (0,))
            domains.extend([(0,1)]*(2*len(ir['atoms'])))
            fixed={a:res[j] for j,a in enumerate(proj['nodes'])}
            for j,a in enumerate(proj['atoms']):
                fixed[n+2*a]=res[m+2*j];fixed[n+2*a+1]=res[m+2*j+1]
            ds=[(fixed[i],) if i in fixed else d for i,d in enumerate(domains)]
            for full in itertools.product(*ds):
                for bit in ('0','1'):
                    actual=native.cell(ir,full,bit);following,_,_=local.derivative(ir,state,bit)
                    projected=[actual[i] for i in proj['nodes']]
                    for a in proj['atoms']:projected.extend(actual[n+2*a:n+2*a+2])
                    self.assertEqual(tuple(projected),following)

    def test_absorbing_guard_every_suffix(self):
        c=self.cert;_,ir,_,_=checker.rebuild(self.text,self.sel,c['source_model'])
        for edge in c['source_model']['edges']:
            if not edge['proof']['retired_equalities']:continue
            st=c['source_model']['states'][edge['state']]
            sliced,_,_=local.view(ir,st);res,_,_=local.derivative(ir,st,edge['symbol'])
            nxt=local.replay_edge(ir,st,edge['symbol'],edge['proof'])
            reduced,_,out=local.view(ir,nxt)
            for size in range(5):
                for suffix in itertools.product('01',repeat=size):
                    a,b=res,out
                    for bit in suffix:a=native.cell(sliced,a,bit);b=native.cell(reduced,b,bit)
                    self.assertEqual(native.terminal(sliced,a),native.terminal(reduced,b))

    def test_renamed_source_same_sizes(self):
        text=source('x==16',name='Renamed',method='test').replace(' x',' input').replace('x==','input==')
        c,r=producer.infer(text,selection(name='Renamed',method='test'))
        self.assertEqual(r['classes'],self.checked['classes'])

    def test_empty_completion_and_streaming(self):
        run,_=runtime.load(self.text,self.sel,self.cert)
        with self.assertRaises(ValueError): run.start().finish()
        self.assertEqual(run.start().terminal,'not-a-word')
        self.assertEqual(run.start().feed('0000').feed('10').finish(),run.value(16,6))

    def test_wide_boundary_words(self):
        text=source('x==2147483648L');c,_=producer.infer(text,self.sel);run,_=runtime.load(text,self.sel,c)
        ir=read_source(text,self.sel['entry'],'long')
        for w in (1,31,32,33,63,64,65,128,4096):
            for x in (0,1,(1<<w)-1,1<<(w-1),2147483648 % (1<<w)):
                self.assertEqual(run.value(x,w),native.evaluate(ir,x,w))

    def test_missing_and_unknown_model_fields(self):
        for k in self.cert['source_model']:
            c=deepcopy(self.cert);del c['source_model'][k];self.reject(c)
        c=deepcopy(self.cert);c['source_model']['guard']='trust';self.reject(c)

    def test_source_and_selection_binding(self):
        with self.assertRaises(ValueError): checker.check_observations(self.text+'\n',self.sel,self.cert)
        with self.assertRaises((ValueError,Unsupported)): checker.check_observations(self.text,selection('int'),self.cert)

    def test_changed_reduction_dependency(self):
        c=deepcopy(self.cert);c['source_model']['reduction']['final_formula']=['literal',True];self.reject(c)

    def test_missing_guard(self):
        c=deepcopy(self.cert)
        edge=next(e for e in c['source_model']['edges'] if e['proof']['retired_equalities'])
        edge['proof']['retired_equalities']=[];self.reject(c)

    def test_false_guard_on_matching_branch(self):
        c=deepcopy(self.cert)
        edge=next(e for e in c['source_model']['edges'] if not e['proof']['retired_equalities'])
        edge['proof']['retired_equalities']=[0];self.reject(c)

    def test_current_signed_flag_cannot_be_retired(self):
        text=source('x<0');c,_=producer.infer(text,self.sel)
        c['source_model']['edges'][1]['proof']['retired_equalities']=[0]
        with self.assertRaises(ValueError):checker.check_observations(text,self.sel,c)

    def test_dropped_live_dependency_and_projection(self):
        c=deepcopy(self.cert);c['source_model']['states'][0]['projection']['nodes']=[0];self.reject(c)
        c=deepcopy(self.cert);c['source_model']['edges'][0]['proof']['dropped']['nodes']=[0];self.reject(c)

    def test_boolean_payload_cannot_be_integer(self):
        c=deepcopy(self.cert);s=next(s for s in c['source_model']['states'] if s['formula'][0]=='literal')
        s['formula'][1]=0;self.reject(c)
        c=deepcopy(self.cert);c['source_model']['states'][0]['residual'][0]=False;self.reject(c)

    def test_step_rule_not_valid_at_cut(self):
        c=deepcopy(self.cert);c['source_model']['edges'][0]['proof']['steps']=[{'rule':'eq-reflexive','path':[]}]
        self.reject(c)

    def test_both_binary_branches_required(self):
        c=deepcopy(self.cert);c['source_model']['edges'].pop();self.reject(c)
        c=deepcopy(self.cert);c['source_model']['edges'][1]=deepcopy(c['source_model']['edges'][0]);self.reject(c)

    def test_duplicate_state_and_false_reachability(self):
        c=deepcopy(self.cert);c['source_model']['states'][1]=deepcopy(c['source_model']['states'][0]);self.reject(c)
        c=deepcopy(self.cert);c['source_model']['parents'][1]=[1,'0'];self.reject(c)
        c=deepcopy(self.cert);c['source_model']['parents'][1]=[0,'1'];self.reject(c)

    def test_false_transition_and_terminal(self):
        c=deepcopy(self.cert);c['source_model']['edges'][0]['next']=2;self.reject(c)
        c=deepcopy(self.cert);c['source_model']['model']['terminal']['g000']='true';self.reject(c)

    def test_generic_proof_of_forged_model_rejected(self):
        from research.observations.producer import synthesize
        from research.observations.checker import check
        c=deepcopy(self.cert);data=c['source_model']['model']
        key=next(k for k,v in data['terminal'].items() if v=='false');data['terminal'][key]='true'
        proof=synthesize(data,row_encoding='atomic')['certificate'];check(data,proof)
        c['observations']=proof;self.reject(c)

    def test_changed_atoms_and_cells_rejected(self):
        c=deepcopy(self.cert);c['observations']['rows'][0]['supplied'][0][1]^=1;self.reject(c)
        c=deepcopy(self.cert);c['observations']['cells'][0]['next']=999;self.reject(c)

    def test_no_unchecked_source_receipt_used_for_target(self):
        with self.assertRaises(InvalidProof):v6.check(self.text,target(),self.cert)
        with self.assertRaises(ValueError):targets.check(self.text,target(),{'schema':targets.SCHEMA})

    def test_correct_tautology_goal_now_certified(self):
        text=source('x == 2147483648L || x != 2147483648L')
        result,proof=v6.prove(text,target(TRUE));self.assertEqual(result['status'],'certified')
        self.assertEqual(v6.check(text,target(TRUE),proof),result)
        self.assertEqual(result['inner']['runtime']['coverage']['covered_states'],2)
        result,_=v4.prove(text,target(TRUE));self.assertEqual(result['status'],'budget_exhausted')

    def test_equality_gets_actual_target_refutation(self):
        result,proof=v6.prove(source('x==2147483648L'),target())
        self.assertEqual(result['status'],'refuted')
        self.assertEqual(result['inner']['target']['witness_width'],1)
        self.assertEqual(v6.check(source('x==2147483648L'),target(),proof),result)

    def test_target_substitution_rehashed_still_checked(self):
        text=source('true');_,p=v6.prove(text,target(TRUE))
        c=deepcopy(p['proof']);compiled,sel=targets.prepare(target())
        run,receipt=runtime.load(text,sel,c['observations']);c['binding']=targets.binding(compiled,receipt)
        with self.assertRaises(ValueError):targets.check(text,target(),c)

    def test_goal_does_not_change_observation_package(self):
        text=source('x==16');_,a=v6.prove(text,target());_,b=v6.prove(text,target(TRUE))
        self.assertEqual(a['proof']['observations'],b['proof']['observations'])

    def test_incomplete_target_product(self):
        text=source('x<0');goal=target(['negative']);_,p=v6.prove(text,goal)
        p['proof']['obligation']['states'].pop()
        with self.assertRaises(InvalidProof):v6.check(text,goal,p)

    def test_saved_result_and_schema_substitution(self):
        text=source('true');goal=target(TRUE);_,p=v6.prove(text,goal)
        p['result']['inner']['runtime']['coverage']['covered_states']=0
        with self.assertRaises(InvalidProof):v6.check(text,goal,p)
        with self.assertRaises(InvalidProof):v4.check(text,goal,p)

    def test_positive_product_never_evaluates_whole_words(self):
        with mock.patch.object(native,'evaluate',side_effect=AssertionError('no sampling for positive proof')):
            r,p=v6.prove(source('x<0'),target(['negative']))
            self.assertEqual(v6.check(source('x<0'),target(['negative']),p),r)

    def test_legacy_positive_and_concrete_replay(self):
        text=source('x<0');goal=target(['negative']);r,p=v4.prove(text,goal)
        self.assertEqual(v6.check(text,goal,p),r)
        text=source('true');goal=target();r,p=v5.witness(text,goal,0,1)
        self.assertEqual(v6.check(text,goal,p),r)

    def test_runtime_detached_and_row_only(self):
        c=deepcopy(self.cert);run,_=runtime.load(self.text,self.sel,c);c.clear()
        with mock.patch.object(native,'cell',side_effect=AssertionError('no residual after load')):
            self.assertEqual(run.value(16,6),True)
        self.assertEqual(set(run.__slots__),{'machine','identity'})

    def test_separate_budget_stages(self):
        for expr,opts,stage in [('x==256 || x!=256',{'max_steps':0},'source_reduction'),
                                ('x==256 && x>0',{'max_local_steps':0},'guarded_coverage'),
                                ('x==16',{'max_states':1},'guarded_coverage'),
                                ('x==16',{'max_observations':0},'observation_closure')]:
            c,r=producer.infer(source(expr),self.sel,**opts)
            self.assertIsNone(c);self.assertEqual(r['stage'],stage)
        r,p=v6.prove(source('true'),target(TRUE),budgets={'max_target_states':1})
        self.assertIsNone(p);self.assertEqual(r['inner']['stage'],'target_product')

    def test_unknown_or_invalid_budgets(self):
        for val in ({'x':1},{'max_states':65},{'max_local_steps':True},{'max_steps':-1}):
            with self.assertRaises(ValueError):v6.prove(self.text,target(),budgets=val)

    def test_unsupported_dead_operation_not_erased(self):
        c,r=producer.infer(source('true',prefix='long dead=x>>1;'),self.sel)
        self.assertIsNone(c);self.assertEqual(r['status'],'unsupported')

    def test_explain_checks_first(self):
        info=checker.explain(self.text,self.sel,self.cert);self.assertTrue(info['erasures'])
        c=deepcopy(self.cert);c['source_model']['edges'][0]['next']=2
        with self.assertRaises(ValueError):checker.explain(self.text,self.sel,c)

    def test_fresh_guarded_source_and_target_replay(self):
        text=source('x<0');goal=target(['negative']);r,p=v6.prove(text,goal)
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'case.json';f.write_text(json.dumps([self.text,self.sel,self.cert,text,goal,p]))
            code='''import importlib.abc,json,sys
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname.endswith('.producer') or '.producer_' in fullname or fullname.split('.')[0] in {'subprocess','z3','cvc5','pysmt'}:
   raise ImportError('blocked '+fullname)
sys.meta_path.insert(0,Guard());sys.path.insert(0,sys.argv[1])
from research.signed_coverage.checker import check_observations
from research.unified.v6 import check,explain
s,q,c,t,g,p=json.load(open(sys.argv[2]));check_observations(s,q,c);check(t,g,p);explain(t,g,p)
print('guarded replay passed')'''
            for flags in ([],['-O']):
                done=subprocess.run([sys.executable,'-I','-B',*flags,'-c',code,str(ROOT),str(f)],capture_output=True,text=True)
                self.assertEqual(done.returncode,0,done.stderr)

    def test_non_signed_discovery_preserves_legacy_identity(self):
        from research.unified.experiment import WORD_SOURCE, WORD_TARGET, PRED_SOURCE, PRED_TARGET
        for text,goal in ((WORD_SOURCE,WORD_TARGET),(PRED_SOURCE,PRED_TARGET)):
            self.assertEqual(v6.prove(text,goal),v4.prove(text,goal))

    def test_product_calls_only_checked_rows_after_loading(self):
        from research.signed_targets.common import Monitor
        from research.signed_targets.checker import check_product
        text=source('x<0');goal=target(['negative']);_,p=v6.prove(text,goal)
        compiled,sel=targets.prepare(goal);run,_=runtime.load(text,sel,p['proof']['observations'])
        def profile(frame,event,arg):
            name=frame.f_globals.get('__name__','')
            if event=='call' and name.startswith('research.') and not name.startswith((
                'research.signed_targets','research.signed_runtime',
                'research.signed_predicates.frontend','research.observations.model')):
                raise AssertionError('source/coverage work inside target product: '+name)
        sys.setprofile(profile)
        try:self.assertEqual(check_product(Monitor(run,compiled['specification']),p['proof']['obligation'])['status'],'certified')
        finally:sys.setprofile(None)

    def test_retained_limitation_not_minimal_construction(self):
        text=source('x != 2147483648L || (x & 1) == 0')
        c,r=producer.infer(text,self.sel)
        self.assertEqual(r['coverage']['covered_states'],34)
        self.assertEqual(r['classes'],2)  # Absorbing-false guards do not derive every invariant.

    def test_cli_roundtrip_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);s=d/'Demo.java';s.write_text(self.text);c=d/'c.json'
            args=[str(s),'--class','Demo','--method','f','--word-type','long','--certificate',str(c)]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(['infer',*args]),0)
                self.assertEqual(cli.main(['check',*args]),0)
                self.assertEqual(cli.main(['explain',*args]),0)
                self.assertEqual(cli.main(['infer',*args]),64)
                c.write_text('{"schema":1,"schema":2}')
                self.assertEqual(cli.main(['check',*args]),3)

    def test_unified_cli_positive_and_refuted(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);s=d/'Demo.java';g=d/'goal.json';p=d/'proof.json'
            s.write_text(source('true'));g.write_text(json.dumps(target(TRUE)))
            args=[str(s),'--target',str(g),'--proof',str(p)]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(v6.main(['prove',*args]),0)
                self.assertEqual(v6.main(['check',*args]),0)
                self.assertEqual(v6.main(['explain',*args]),0)
                self.assertEqual(v6.main(['prove',*args]),64)
                g.write_text(json.dumps(target()))
                self.assertEqual(v6.main(['check',*args]),3)


if __name__=='__main__':unittest.main()
