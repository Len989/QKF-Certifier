"""Typed parsing, terminal closure, damaged proofs and native-width separation."""
import contextlib
import copy
import io
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from research.observations.model import digest
from .frontend import Unsupported
from .predicate_checker import check
from .predicate_cli import main
from .predicate_frontend import CONTRACT, GOAL_SCHEMA, goal, read_source, target_value
from .predicate_producer import Budget, derive
from .predicate_semantics import cell, evaluate, initial, terminal


def source(body='return (x & (x - 1)) == 0;', typ='int', name='f'):
    return 'class Example { public static boolean '+name+'('+typ+' x) {'+body+'} }'


def spec(target=None, typ='int', name='f'):
    return {'schema': GOAL_SCHEMA, 'contract': CONTRACT, 'entry': {'class': 'Example', 'method': name},
            'word_type': typ, 'target': ['popcount_le', 1] if target is None else target}


def streamed(ir, x, w):
    s = initial(ir)
    for i in range(w):
        s = cell(ir, s, str((x >> i) & 1))
    return terminal(ir, s)


class ParsingTests(unittest.TestCase):
    def reject(self, text, typ='int'):
        with self.assertRaises(Unsupported):
            read_source(text, spec(typ=typ)['entry'], typ)

    def test_int_and_long(self):
        self.assertEqual(derive(source(), spec())[1]['java_width'], 32)
        text = source('return (x & (x - 1L)) == 0L;', 'long')
        self.assertEqual(derive(text, spec(typ='long'))[1]['java_width'], 64)

    def test_name_does_not_choose_property(self):
        r = derive(source('return false;', name='isZeroOrPowerOfTwo'), spec(name='isZeroOrPowerOfTwo'))[1]
        self.assertEqual(r['status'], 'refuted')
        self.assertEqual(r['input'], 0)

    def test_typed_locals(self):
        text = source('int t=x-1; boolean z=(x & t)==0; return z;')
        self.assertEqual(derive(text, spec())[1]['status'], 'certified')

    def test_reassigned_words_and_booleans(self):
        text = source('boolean z=x==0; int t=x; x=x-1; z=(x & t)==0; return z;')
        self.assertEqual(derive(text, spec())[1]['status'], 'certified')

    def test_final_assignments(self):
        self.reject(source('final int t=x; t=0; return t==0;'))
        self.reject(source('final boolean t=true; t=false; return t;'))
        self.reject(source().replace('int x', 'final int x').replace('return', 'x=0; return'))

    def test_no_mixed_literals_or_conversions(self):
        for body in ('return x==0L;', 'long t=x; return t==0L;', 'return (long)x==0L;', 'return 1L+1L==2L;'):
            self.reject(source(body))
        self.reject(source('return x==0;', 'long'), 'long')

    def test_strict_literal_grammar(self):
        for value in ('01','0xff','1_000','2147483648','2147483649','0b1'):
            self.reject(source('return x=='+value+';'))
        self.reject(source('return x==9223372036854775808L;', 'long'), 'long')

    def test_int_overload_selected_not_long(self):
        text = source().replace('public static', 'static boolean f(long x){return false;} public static')
        self.assertEqual(derive(text, spec())[1]['status'], 'certified')

    def test_nested_and_fake_not_selected(self):
        text = source().replace('public static', 'class Inner { static boolean f(int x){return false;} } public static')
        text = '/* class Example {} */'+text
        self.assertEqual(derive(text, spec())[1]['status'], 'certified')

    def test_duplicate_declarations(self):
        self.reject(source()+source())
        self.reject(source().replace('public static', 'static boolean f(int x){return false;} public static'))

    def test_static_and_annotations(self):
        self.reject(source().replace('static ', ''))
        self.reject(source().replace('public static', '@Deprecated public static'))

    def test_reject_non_boolean_and_ill_typed(self):
        for b in ('return x;', 'return !x;', 'return ~true;', 'return x && true;',
                  'return true + 1;', 'return true & false;', 'return x==0==true;',
                  'int t=true; return false;', 'boolean b=x; return b;',
                  'boolean b=true; b=x; return b;', 'return x & x-1 == 0;'):
            self.reject(source(b))

    def test_no_calls_fields_shifts_casts_effects(self):
        for b in ('return f(x);', 'return x>0;', 'return (x>>1)==0;', 'return (x<<1)==0;',
                  'return (int)x==0;', 'return x++==0;', 'return x--==0;', 'return x*2==0;',
                  'return Example.x==0;', 'if(x==0)return true; return false;',
                  'return true; x=0;', 'return x==0 ? true : false;'):
            self.reject(source(b))

    def test_boolean_precedence(self):
        ir = read_source(source('return x==0 || x==1 && false;'), spec()['entry'], 'int')
        for x in range(16):
            self.assertEqual(evaluate(ir,x,4),x==0)

    def test_unary_equality_parentheses(self):
        r = derive(source('return !((x & (x-1)) != 0);'), spec())[1]
        self.assertEqual(r['status'], 'certified')

    def test_undefined_duplicate_and_missing_return(self):
        for b in ('return y==0;', 'int x=0; return true;', 'boolean class=true; return class;',
                  'int t=t; return t==0;', 'int t=x;'):
            self.reject(source(b))

    def test_unicode_and_lexical_exclusions(self):
        self.reject(source().replace('return',r'\u0072eturn'))
        self.reject(source()+' /* unterminated')
        self.reject(source().replace('return', '"""x""" return'))

    def test_bool_expansion_budget(self):
        self.reject(source('boolean b=x==0;'+'b=b&&b;'*10+'return b;'))


class CertificateTests(unittest.TestCase):
    def setUp(self):
        self.text, self.spec = source(), spec()
        self.cert, self.result = derive(self.text, self.spec)

    def test_real_observations_and_terminal_labels(self):
        self.assertEqual((self.result['source']['native_states'],self.result['source']['classes'],
                          self.result['product_states'],self.result['checked_edges']), (4,3,3,6))
        self.assertEqual(check(self.text,self.spec,self.cert),self.result)
        self.assertTrue(any(p['kind']=='terminal' for p in self.cert['source']['observations']['predicates']))

    def test_equivalent_and_independent_targets(self):
        for b in ('return (x & -x)==x;', 'return ((x ^ (x-1)) & x)==x;'):
            self.assertEqual(derive(source(b),spec())[1]['status'],'certified')
        text=source('return ((x & (x-1))==0) && x!=0;')
        self.assertEqual(derive(text,spec(['popcount_eq',1]))[1]['status'],'certified')
        self.assertEqual(derive(source('return x==0;'),spec(['popcount_eq',0]))[1]['status'],'certified')

    def test_saturating_count_two_and_three(self):
        for k in (2,3):
            body='int t=x; '+'t=t & (t-1); '*k+'return t==0;'
            self.assertEqual(derive(source(body),spec(['popcount_le',k]))[1]['status'],'certified')

    def test_boolean_target_connectives(self):
        g=spec(['or',['popcount_eq',0],['popcount_eq',1]])
        self.assertEqual(derive(source(),g)[1]['status'],'certified')
        g=spec(['and',['not',['popcount_eq',0]],['popcount_le',1]])
        self.assertEqual(derive(source('return x!=0 && ((x & (x-1))==0);'),g)[1]['status'],'certified')

    def test_bad_programs_and_zero(self):
        for body in ('return true;','return false;','return x==0;','return (x & (x+1))==0;',
                     'return (x & (x-1))!=0;','return x!=0 && ((x & (x-1))==0);'):
            c,r=derive(source(body),spec())
            self.assertEqual(r['status'],'refuted')
            self.assertEqual(check(source(body),spec(),c),r)
            self.assertNotEqual(r['output'],r['expected'])

    def test_terminal_not_first_bit(self):
        ir=self.cert['source']['ir']; s=initial(ir)
        s=cell(ir,s,'1');self.assertTrue(terminal(ir,s))
        s=cell(ir,s,'1');self.assertFalse(terminal(ir,s))
        s=cell(ir,s,'0');self.assertFalse(terminal(ir,s))

    def test_original_zero_minimum_int_unsigned_power(self):
        ir=self.cert['source']['ir']
        self.assertTrue(evaluate(ir,0,32))
        self.assertTrue(evaluate(ir,1<<31,32))
        self.assertFalse(evaluate(ir,(1<<32)-1,32))

    def test_counterexample_is_not_automatically_native(self):
        # This is identically true at native width, but false at mathematical w=1.
        text=source('return 2 != 0;')
        g=spec(['or',['popcount_le',1],['not',['popcount_le',1]]])
        c,r=derive(text,g)
        self.assertEqual(r['status'],'refuted');self.assertEqual(r['width'],1)
        self.assertFalse(r['native_width_check']['violates_goal'])
        self.assertEqual(check(text,g,c),r)

    def test_source_binding(self):
        with self.assertRaises(ValueError): check(self.text+' ',self.spec,self.cert)
        g=spec();g['entry']['method']='renamed'
        with self.assertRaises(ValueError): check(self.text,g,self.cert)

    def test_wrong_type_and_goal(self):
        for key,val in [('word_type','long'),('target',['popcount_eq',1])]:
            g=spec();g[key]=val
            with self.assertRaises(ValueError):check(self.text,g,self.cert)

    def test_rehashed_goal_no_fake_proof(self):
        c=copy.deepcopy(self.cert);g=spec(['popcount_eq',1]);c['goal_sha256']=digest(g)
        with self.assertRaisesRegex(ValueError,'terminal predicate'): check(self.text,g,c)

    def test_ir_carrier_and_terminal_corruption(self):
        for kind in ('ir','start','parent','truncate','boolflag','atom'):
            c=copy.deepcopy(self.cert);rows=c['source']['carrier']
            if kind=='ir': c['source']['ir']['nodes'][-1][0]='or'
            elif kind=='start':rows[0]['state'][-1]=1
            elif kind=='parent':rows[1]['parent']=[1,'0']
            elif kind=='truncate':rows.pop()
            elif kind=='boolflag':rows[0]['state'][-1]=False
            else:c['source']['ir']['atoms'][0].reverse()
            with self.assertRaises(ValueError):check(self.text,self.spec,c)

    def test_qkf_rows_checked(self):
        c=copy.deepcopy(self.cert);c['source']['observations']['rows'][0]['supplied'][0][1]^=1
        with self.assertRaises(ValueError):check(self.text,self.spec,c)

    def test_property_states_corrupted(self):
        for kind in ('start','parent','truncate','flag','extra'):
            c=copy.deepcopy(self.cert);rows=c['proof']['states']
            if kind=='start':rows[0]['state'][1]=1
            elif kind=='parent':rows[1]['parent']=[1,'1']
            elif kind=='truncate':rows.pop()
            elif kind=='flag':rows[0]['state'][0]=False
            else:c['proof']['extra']=None
            with self.assertRaises(ValueError):check(self.text,self.spec,c)

    def test_witness_types_and_values(self):
        text=source('return true;');c,_=derive(text,spec())
        for k,v in [('bits',''),('input',True),('input',0),('output',1),('expected',0),('output',False)]:
            bad=copy.deepcopy(c);bad['proof'][k]=v
            with self.assertRaises(ValueError):check(text,spec(),bad)

    def test_budget_failures(self):
        with self.assertRaises(Budget):derive(source(),spec(),max_states=1)
        with self.assertRaises(Budget):derive(source(),spec(),max_product=1)
        with self.assertRaises(ValueError):derive(source(),spec(),max_states=True)

    def test_spec_validation(self):
        for t in (['popcount_le',True],['popcount_eq',4],['popcount_eq',-1],['call',0],
                  ['popcount_le',1,2],['not'],['and',['popcount_eq',0]]):
            with self.assertRaises(ValueError):goal(spec(t))
        g=spec();g['assume']=False
        with self.assertRaises(ValueError):goal(g)

    def test_wide_word_count_bridge(self):
        ir=self.cert['source']['ir'];rng=random.Random(1617)
        for w in (1,2,31,32,33,63,64,65,127,256,4096):
            for x in (0,1,1<<(w-1),(1<<w)-1,rng.getrandbits(w)):
                self.assertEqual(streamed(ir,x,w),x.bit_count()<=1)

    def test_random_predicate_cut_bridge(self):
        rng=random.Random(20260917)
        def term(d):
            if d==0:return rng.choice(['x','0','1','2','7'])
            return '('+term(d-1)+rng.choice(['+','-','&','|','^'])+term(d-1)+')'
        for _ in range(30):
            text=source('return ('+term(2)+'=='+term(2)+') || (x==0);')
            ir=read_source(text,spec()['entry'],'int')
            for w in range(1,7):
                for x in range(1<<w):self.assertEqual(streamed(ir,x,w),evaluate(ir,x,w))

    def test_no_producer_fresh_process(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'case.json';p.write_text(json.dumps([self.text,self.spec,self.cert]))
            code='''import json,sys,importlib.abc
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if any(s in fullname for s in ('producer','synthesis','subprocess','z3','smt','java_words','ascending_java')):
   raise ImportError('forbidden:'+fullname)
sys.meta_path.insert(0,Block())
from research.wordexpr.predicate_checker import check
s,g,c=json.load(open(sys.argv[1]));print(json.dumps(check(s,g,c),sort_keys=True))
'''
            for flags in ([],['-O']):
                p1=subprocess.run([sys.executable,*flags,'-c',code,str(p)],capture_output=True,text=True,timeout=20)
                self.assertEqual(p1.returncode,0,p1.stderr)
                self.assertEqual(json.loads(p1.stdout),self.result)

    def test_cli_preserves_existing_output_and_duplicate_json(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);src=d/'x.java';g=d/'g.json';c=d/'c.json'
            src.write_text(source());g.write_text(json.dumps(spec()))
            args=['prove',str(src),'--spec',str(g),'--certificate',str(c)]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(args),0);old=c.read_bytes()
                self.assertEqual(main(args),64);self.assertEqual(c.read_bytes(),old)
                args[0]='check';self.assertEqual(main(args),0)
                c.write_text('{"a":1,"a":2}')
                self.assertEqual(main(args),3)


if __name__=='__main__':
    unittest.main()
