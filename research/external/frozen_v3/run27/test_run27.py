"""Supervisor/inventory corruption tests. No external candidate is evaluated."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gate
import inventory
import runner


class Run27Tests(unittest.TestCase):
    def test_duplicate_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'bad.json'; p.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError): gate.load(p)

    def test_nonfinite_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'bad.json'; p.write_text('{"a":NaN}')
            with self.assertRaises(ValueError): gate.load(p)

    def test_normalized_local_names(self):
        self.assertEqual(inventory.normalize('{int y=x+1;return y;}', ['x','y']),
                         inventory.normalize('{ int b = a + 1; /* local */ return b; }', ['a','b']))

    def test_member_names_retained(self):
        self.assertNotEqual(inventory.normalize('{return x.a;}', ['x','a']),
                            inventory.normalize('{return y.b;}', ['y','b']))

    def test_utf16_span(self):
        self.assertEqual(inventory.char_position('a\U0001f642b', 3), 2)

    def test_literal_comments_retained(self):
        self.assertIn('"//not a comment"', inventory.tokens('"//not a comment" /* gone */'))

    def test_population_deterministic(self):
        a = runner.population('constructed', 32)
        self.assertEqual(a, runner.population('constructed', 32))
        self.assertEqual(a, sorted(set(a)))
        self.assertTrue(set(range(65536)) <= set(a))

    def test_population_identity(self):
        self.assertNotEqual(runner.population('a', 32), runner.population('b', 32))

    def test_population_boundaries(self):
        for w in (32,64):
            p = runner.population('constructed', w, [123456789])
            self.assertTrue({(1 << w)-1, 1 << (w-1), (1 << (w-1))-1, 123456789} <= set(p))
            self.assertTrue(all(0 <= v < 1 << w for v in p))

    def test_inventory_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            text = '''class Outer {
                public static int a(int x) {return x;}
                static public long b(final long x) {return x;}
                public static native int c(int x);
                public static int nope(int... x) {return 0;}
                public static int array(int[] x) {return 0;}
                static int hidden(int x) {return x;}
                class Inner {public static boolean nested(int x) {return x==0;}}
            }'''
            p = data / 'Outer.java'; p.write_text(text)
            frame = {'repositories':[{'repository':'constructed','revision':'test',
                     'frame':[{'source_file':'Outer.java','sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'git_blob':'test'}]}]}
            (data / 'FRAME.json').write_text(json.dumps(frame))
            rows, diagnostics = inventory.inventory(data)
            selected = [r for r in rows if r['eligible']]
            self.assertEqual([r['method'] for r in selected], ['a','b','c','nested'])
            self.assertEqual(selected[-1]['class'], 'Outer.Inner')
            self.assertIsNone(selected[2]['body_span'])
            self.assertEqual(diagnostics, '')

    def test_supervisor_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = runner.supervise([sys.executable, '-I', '-c', 'import time;time.sleep(2)'], Path(tmp)/'process', 0.05)
            self.assertTrue(m['timeout']); self.assertLess(m['exit_code'], 0)
            self.assertGreater(m['peak_rss_kib'], 0)

    def test_nonzero_is_not_oom(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = runner.supervise([sys.executable, '-I', '-c', 'raise SystemExit(7)'], Path(tmp)/'process')
            self.assertEqual(m['exit_code'], 7); self.assertFalse(m['timeout'])
            self.assertIn('no_automatic_OOM', m['memory_classification'])

    def test_runtime_drift(self):
        with patch('acquire.runtime', return_value={}), patch('platform.python_version', return_value='not-registered'):
            with self.assertRaisesRegex(ValueError, 'unregistered Python'):
                gate.runtime_check()

    def test_missing_execution_authorization(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(gate, 'HERE', Path(tmp)), patch.object(gate, 'verify_seals'):
            with self.assertRaises(FileNotFoundError): gate.verify_execution()

    def test_source_span_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp); (data/'FRAME.json').write_text('{}'); (data/'demo').write_text('abc')
            corpus = {'source_frames':[], 'frame_sha256': gate.sha((data/'FRAME.json').read_bytes()),
                      'cases':[{'source_file':'demo','span':[0,2],'declaration_sha256':gate.sha(b'wrong'),
                                'body_span':None,'body_sha256':None,'doc_span':None,'doc_sha256':None}]}
            with self.assertRaisesRegex(ValueError, 'span'): gate.verify_inputs(corpus,data,False)

    def test_constructed_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            declaration = 'public static boolean p(int x) {return x > 0 && (x & (x-1)) == 0;}'
            source = 'class Demo {' + declaration + '}'
            source_path = folder / 'Demo.java'; source_path.write_text(source)
            case = {'case_id':'constructed-only','class':'Demo','method':'p','return_type':'boolean',
                    'parameter_types':['int'],'source_diagnostic_route':'signed','span':[12,12+len(declaration)],
                    'declaration_sha256':gate.sha(declaration.encode()),'contract_state':'registered_goal',
                    'target':{'schema':'qkf-target-v2','kind':'signed_boolean_predicate',
                              'source':{'entry':{'class':'Demo','method':'p'},'word_type':'int'},
                              'goal':['and',['positive'],['popcount_eq',1]]}}
            request = {'mode':'discover','case':case,'source_path':str(source_path),'source_sha256':gate.sha(source.encode()),
                       'budgets':{'max_features':128,'max_target_states':8192}}
            metrics = runner.worker(gate.ROOT, folder, request, 'discover')
            self.assertEqual(metrics['exit_code'], 0, (folder/'discover-process/stderr.log').read_text())
            row = gate.load(folder/'discover/result.json'); self.assertEqual(row['classification'], 'certified')
            replay = {**request,'mode':'replay','proof_path':str(folder/'discover/proof.json')}
            m = runner.worker(gate.ROOT,folder,replay,'replay',True)
            self.assertEqual(m['exit_code'],0)
            result = runner.native(gate.ROOT, folder, case, request, row)
            self.assertEqual(result['status'],'matched', result)
            self.assertEqual(result['source_ir_mismatches'],[])
            proof = gate.load(folder/'discover/proof.json'); proof['binding']['source_sha256'] = '0'*64
            (folder/'corrupt.json').write_text(json.dumps(proof))
            m = runner.worker(gate.ROOT,folder,{**replay,'proof_path':str(folder/'corrupt.json')},'bad-replay',True)
            self.assertEqual(m['exit_code'],3)
            self.assertEqual(gate.load(folder/'bad-replay/result.json')['classification'],'invalid_certificate')


if __name__ == '__main__':
    unittest.main()
