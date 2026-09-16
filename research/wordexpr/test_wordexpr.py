"""Unit, mathematical correspondence, corruption and isolated no-search tests."""
import copy
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from research.observations.model import digest
from .checker import check
from .cli import load, main, save
from .frontend import CONTRACT, Unsupported, goal, read_source
from .producer import Budget, derive
from .semantics import cell, evaluate, goal_value, initial


def source(body='return x & -x;', name='f', parameter='long x'):
    return 'public class Example { public static long ' + name + '(' + parameter + ') {' + body + '} }'


def spec(target=None, name='f'):
    return {'schema': 'qkf-word-expression-goal-v1', 'contract': CONTRACT,
            'entry': {'class': 'Example', 'method': name},
            'target': ['lowest_set_bit'] if target is None else ['equals', target]}


def streamed(ir, x, width):
    state, y = initial(ir), 0
    for k in range(width):
        b, state = cell(ir, state, str((x >> k) & 1))
        y |= int(b) << k
    return y


class FrontendTests(unittest.TestCase):
    def reject(self, text):
        with self.assertRaises(Unsupported):
            read_source(text, spec()['entry'])

    def test_explicit_renamed_entry(self):
        c, r = derive(source(name='different'), spec(name='different'))
        self.assertEqual(r['status'], 'certified')
        self.assertEqual(check(source(name='different'), spec(name='different'), c), r)

    def test_no_name_semantics(self):
        c, r = derive(source('return 0L;', name='lowestOneBit'), spec(name='lowestOneBit'))
        self.assertEqual(r['status'], 'refuted')
        self.assertEqual(r['input'], 1)

    def test_locals_and_reassignments(self):
        _, r = derive(source('long t = ~x; t = t + 1L; return t & x;'), spec())
        self.assertEqual(r['status'], 'certified')

    def test_parameter_reassignment(self):
        _, r = derive(source('x = x - 1L; return x + 1L;'), spec(['input']))
        self.assertEqual(r['status'], 'certified')

    def test_final_parameter_and_local(self):
        self.reject(source('x = 0L; return x;', parameter='final long x'))
        self.reject(source('final long t = x; t = 0L; return t;'))

    def test_fake_declarations_ignored(self):
        text = '/* class Example { long f(long x){return 0L;} } */\n' + source()
        self.assertEqual(derive(text, spec())[1]['status'], 'certified')
        text = source().replace('public static', 'String s = "class Example { long f(long x) {} }"; public static')
        self.assertEqual(derive(text, spec())[1]['status'], 'certified')

    def test_overloaded_and_nested_methods(self):
        text = source().replace('public static', 'public static long f(int x) { return 0L; } class Inner { static long f(long x){return 0L;} } public static')
        self.assertEqual(derive(text, spec())[1]['status'], 'certified')

    def test_duplicate_selected_declaration(self):
        self.reject(source().replace('public static', 'public static long f(long y){return y;} public static'))
        self.reject(source() + source())

    def test_no_static(self):
        self.reject(source().replace('static ', ''))

    def test_long_literals_only(self):
        for body in ('return x-1;', 'return 0xffL;', 'return 01L;', 'return 9223372036854775808L;'):
            self.reject(source(body))

    def test_no_effects_calls_casts_shifts(self):
        for body in ('return x--;', 'return x++ + 1L;', 'return x--1L;', 'return x >> 1L;',
                     'return Long.lowestOneBit(x);', 'return (int)x;', 'return x * x;',
                     'return x; x = 0L;', 'while(true){} return x;', 'return x > 0L ? x : 0L;'):
            self.reject(source(body))

    def test_undefined_duplicate_reserved_local(self):
        for body in ('return absent;', 'long x = 1L; return x;', 'long class = 1L; return class;',
                     'long t = t; return t;', 'long t = x;'):
            self.reject(source(body))

    def test_unicode_and_unterminated(self):
        self.reject(source().replace('return', r'\u0072eturn'))
        self.reject('/* ' + source())
        self.reject('// ' + r'\u000a' + source())
        self.reject(source('return x; /* no end'))
        self.assertEqual(derive('/* '+r'\u005Cu002d'+' */'+source(), spec())[1]['status'], 'certified')

    def test_precedence(self):
        ir = read_source(source('return x & -x + 1L;'), spec()['entry'])
        for x in range(256):
            self.assertEqual(evaluate(ir, x, 8), x & ((-x + 1) & 255))

    def test_depth_limit(self):
        self.reject(source('return ' + '~' * 40 + 'x;'))


class ProofTests(unittest.TestCase):
    def setUp(self):
        self.text, self.goal = source(), spec()
        self.cert, self.result = derive(self.text, self.goal)

    def test_real_generic_factor(self):
        self.assertEqual(self.result['source']['native_states'], 2)
        self.assertEqual(self.result['source']['classes'], 2)
        self.assertEqual(self.result['product_states'], 2)
        self.assertTrue(self.result['all_positive_widths'])

    def test_generic_algebra_not_one_template(self):
        cases = [('return (x - 1L) + 1L;', ['input']),
                 ('return (x + 2L) - 2L;', ['input']),
                 ('return ~x + 1L;', ['neg', ['input']]),
                 ('return x | ~x;', ['not', ['const', 0]]),
                 ('return (x ^ x) + x;', ['input']),
                 ('return x + x;', ['add', ['input'], ['input']])]
        for body, target in cases:
            self.assertEqual(derive(source(body), spec(target))[1]['status'], 'certified')
        self.assertEqual(derive(source('return x & (~x + 1L);'), spec())[1]['status'], 'certified')

    def test_wrong_programs_refuted(self):
        for body in ('return x & ~x;', 'return x;', 'return x | -x;', 'return x & (x - 1L);'):
            c, r = derive(source(body), spec())
            self.assertEqual(r['status'], 'refuted')
            self.assertNotEqual(r['output'], r['expected'])
            self.assertEqual(check(source(body), spec(), c), r)

    def test_source_and_goal_substitution(self):
        with self.assertRaises(ValueError): check(self.text + ' ', self.goal, self.cert)
        with self.assertRaises(ValueError): check(self.text, spec(['input']), self.cert)

    def test_rehashed_weak_goal(self):
        weak = source('return 0L;')
        c, _ = derive(weak, spec(['const', 0]))
        c['goal_sha256'] = digest(spec())
        with self.assertRaises(ValueError): check(weak, spec(), c)

    def test_ir_and_carrier_corruption(self):
        for field in ('ir', 'start', 'parent', 'closure'):
            c = copy.deepcopy(self.cert)
            if field == 'ir': c['source']['ir']['nodes'][-1][0] = 'or'
            elif field == 'start': c['source']['carrier'][0]['state'][1] = -1
            elif field == 'parent': c['source']['carrier'][1]['parent'][1] = '0'
            else: c['source']['carrier'].pop()
            with self.assertRaises(ValueError): check(self.text, self.goal, c)

    def test_property_corruption(self):
        for kind in ('start', 'parent', 'truncate', 'bool', 'unknown'):
            c = copy.deepcopy(self.cert)
            rows = c['proof']['states']
            if kind == 'start': rows[0]['state'][1] = 1
            elif kind == 'parent': rows[1]['parent'][1] = '0'
            elif kind == 'truncate': rows.pop()
            elif kind == 'bool': rows[0]['state'][0] = False
            else: c['proof']['code'] = 'not executed'
            with self.assertRaises(ValueError): check(self.text, self.goal, c)

    def test_existing_row_checker_is_active(self):
        c = copy.deepcopy(self.cert)
        c['source']['observations']['rows'][0]['supplied'][0][1] ^= 1
        with self.assertRaises(ValueError): check(self.text, self.goal, c)

    def test_counterexample_corruption(self):
        text = source('return x;')
        c, _ = derive(text, spec())
        for field, value in (('input', 0), ('output', 0), ('expected', 0), ('bits', '')):
            changed = copy.deepcopy(c)
            changed['proof'][field] = value
            with self.assertRaises(ValueError): check(text, spec(), changed)

    def test_explicit_budgets(self):
        with self.assertRaises(Budget): derive(self.text, self.goal, max_states=1)
        with self.assertRaises(Budget): derive(self.text, self.goal, max_product=1)

    def test_goal_validation(self):
        for target in (['unknown'], ['equals', ['call', 'x']], ['equals', ['const', True]],
                       ['equals', ['input', 'extra']]):
            g = spec(); g['target'] = target
            with self.assertRaises(ValueError): goal(g)
        g = spec(); g['assume'] = False
        with self.assertRaises(ValueError): goal(g)

    def test_random_expression_arithmetic_bridge(self):
        rng = random.Random(20260916)
        def term(depth):
            if not depth: return rng.choice(['x', '0L', '1L', '2L', '31L'])
            if rng.randrange(3) == 0: return rng.choice(['~', '-']) + '(' + term(depth-1) + ')'
            return '(' + term(depth-1) + ' ' + rng.choice(['+', '-', '&', '|', '^']) + ' ' + term(depth-1) + ')'
        for _ in range(60):
            ir = read_source(source('return '+term(3)+';'), spec()['entry'])
            for w in range(1, 7):
                for x in range(1 << w):
                    self.assertEqual(streamed(ir, x, w), evaluate(ir, x, w))

    def test_wide_lowbit_oracle(self):
        ir = self.cert['source']['ir']
        rng = random.Random(1234)
        for w in (1, 2, 31, 32, 63, 64, 65, 127, 256, 4096):
            for x in (0, 1, 1 << (w-1), (1 << w)-1, rng.getrandbits(w)):
                self.assertEqual(streamed(ir, x, w), goal_value(None, x, w))

    def test_fresh_no_search_processes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'case.json'
            path.write_text(json.dumps([self.text, self.goal, self.cert]))
            code = '''import sys,json,importlib.abc
class Deny(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if any(x in fullname for x in ('producer','synthesize','z3','subprocess','external','ascending','java_words','target_templates')):
   raise ImportError('forbidden '+fullname)
sys.meta_path.insert(0,Deny())
from research.wordexpr.checker import check
r=check(*json.load(open(sys.argv[1])))
if r['status']!='certified': raise SystemExit(1)
'''
            for opts in ([], ['-O']):
                p = subprocess.run([sys.executable, *opts, '-c', code, str(path)], capture_output=True, timeout=10)
                self.assertEqual(p.returncode, 0, p.stderr.decode())


class CLITests(unittest.TestCase):
    def test_roundtrip_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            a, b, c = [Path(d) / x for x in ('s.java', 'g.json', 'proof.json')]
            a.write_text(source()); save(b, spec())
            argv = [str(a), '--spec', str(b), '--certificate', str(c)]
            self.assertEqual(main(['prove', *argv]), 0)
            raw = c.read_bytes()
            self.assertEqual(main(['check', *argv]), 0)
            self.assertEqual(main(['prove', *argv]), 64)
            self.assertEqual(raw, c.read_bytes())

    def test_duplicate_json_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'input.json'
            for s in ('{"x":0,"x":1}', '{"x": NaN}'):
                p.write_text(s)
                with self.assertRaises(ValueError): load(p)


if __name__ == '__main__':
    unittest.main()
