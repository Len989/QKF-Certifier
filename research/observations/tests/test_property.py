"""Independent targets, finite closure, concrete witnesses and replay boundaries."""
import copy
import itertools
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from research.observations.model import digest
from research.observations.property_kernel import System, check
from research.observations.property_producer import synthesize
from research.observations.property_validation import validate
from research.observations.run_property_experiment import variants
from research.observations.source_factor import check as check_source, synthesize as source_producer
from research.observations.upper_spec import check_spec, columns, decode, specification, step

ROOT = Path(__file__).resolve().parents[3]


class PropertyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = variants(); cls.specs = {x: specification(x) for x in ['maximum', 'bound']}
        cls.models = {n: source_producer(s)['certificate'] for n, s in cls.sources.items()}
        cls.certs = {(n, goal): synthesize(s, cls.models[n], cls.specs[goal])['certificate']
                     for n, s in cls.sources.items() for goal in cls.specs}

    def replay(self, name, goal, cert=None):
        return check(self.sources[name], self.models[name], self.specs[goal],
                     self.certs[name, goal] if cert is None else cert)

    def test_original_maximum_and_separate_model_claim(self):
        r = self.replay('original', 'maximum')
        self.assertEqual(r['status'], 'certified')
        self.assertEqual((r['closed_states'], r['checked_transitions']), (49, 980))
        self.assertTrue(r['all_positive_payload_widths']); self.assertFalse(r['native_java_all_widths'])
        self.assertEqual(check_source(self.sources['plus_one'], self.models['plus_one'])['claim'], 'source_model_equivalence')
        self.assertEqual(self.replay('plus_one', 'maximum')['status'], 'refuted')
        with self.assertRaises(ValueError): self.replay('original', 'maximum', self.models['original'])

    def test_maximality_is_stronger_than_a_safe_bound(self):
        for name in ['strict', 'shared_input']:
            self.assertEqual(self.replay(name, 'bound')['status'], 'certified')
            r = self.replay(name, 'maximum')
            self.assertEqual((r['status'], r['reason']), ('refuted', 'not_maximal'))
            self.assertEqual((r['counterexample']['output'], r['counterexample']['alternative']), (0, 1))
        r = self.replay('plus_one', 'bound')
        self.assertEqual((r['counterexample']['bound'], r['counterexample']['output']), (0, 1))

    def test_specification_and_rehashed_weaker_goal(self):
        for mutate in [lambda s:s['preconditions'].pop(), lambda s:s['arguments'].update(bound=4),
                       lambda s:s['arguments'].update(bound=True), lambda s:s.update(extra='trust me'),
                       lambda s:s.update(claim='arbitrary')]:
            spec = copy.deepcopy(self.specs['maximum']); mutate(spec)
            with self.assertRaises(ValueError): check_spec(spec)
        with self.assertRaises(ValueError): self.replay('strict', 'maximum', self.certs['strict', 'bound'])
        cert = copy.deepcopy(self.certs['strict', 'bound'])
        cert['binding']['specification_sha256'] = digest(self.specs['maximum'])
        with self.assertRaisesRegex(ValueError, 'protected target'): self.replay('strict', 'maximum', cert)

    def test_closure_certificate_corruption(self):
        mutations = {
            'missing_state': lambda c:c['states'].pop(),
            'initial_only': lambda c:c.update(states=c['states'][:1]),
            'no_origin': lambda c:c.update(states=[]),
            'duplicate': lambda c:c['states'].append(copy.deepcopy(c['states'][-1])),
            'bool_state': lambda c:c['states'][0]['state'].__setitem__(0, False),
            'order_range': lambda c:c['states'][0]['state'].__setitem__(1, 2),
            'wrong_initial': lambda c:c['states'][0]['state'].__setitem__(1, -1),
            'cycle': lambda c:c['states'][1]['parent'].__setitem__(0, 1),
            'wrong_parent_symbol': lambda c:c['states'][1]['parent'].__setitem__(1, '100000'),
            'wrong_source': lambda c:c['binding'].update(source_sha256='0'*64),
            'wrong_model': lambda c:c['binding'].update(source_certificate_sha256='0'*64),
            'wrong_rule': lambda c:c['binding'].update(target_rules='same-looking-rule'),
            'unknown_field': lambda c:c.update(accepted=True),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                c = copy.deepcopy(self.certs['original', 'maximum']); mutate(c)
                with self.assertRaises(ValueError): self.replay('original', 'maximum', c)

    def test_counterexample_corruption_and_empty_domain(self):
        mutations = {
            'empty': lambda c:c.update(word=[]),
            'illegal_column': lambda c:c.update(word=['001111']),
            'false_reason': lambda c:c.update(reason='not_maximal'),
            'wrong_output': lambda c:c['values'].update(output=0),
            'bool_output': lambda c:c['values'].update(output=True),
            'wrong_width': lambda c:c['values'].update(width=2),
            'unknown_field': lambda c:c.update(proof=[]),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                c = copy.deepcopy(self.certs['plus_one', 'maximum']); mutate(c)
                with self.assertRaises(ValueError): self.replay('plus_one', 'maximum', c)
        c = copy.deepcopy(self.certs['plus_one', 'maximum'])
        c['word'] = ['000111']; c['values'] = decode(c['word'])
        # seed=1 > bound=0 is outside the declared nonempty domain.
        with self.assertRaises(ValueError): self.replay('plus_one', 'maximum', c)

    def test_raw_input_alphabet_and_unread_bound(self):
        expected = []
        for b, must, may, a, y, z in itertools.product(range(2), repeat=6):
            o = may & (1-must)
            if not (a&o) and y in {a, a|o} and z in {a, a|o}:
                expected.append(''.join(map(str, (b,must,may,a,y,z))))
        self.assertEqual(columns(), sorted(expected)); self.assertEqual(len(expected), 20)
        m = System(self.sources['shared_input'], self.models['shared_input'], self.specs['maximum'])
        self.assertEqual(m.projected['001001'], m.projected['101001'])
        self.assertNotEqual(m.advance(m.initial, '001001'), m.advance(m.initial, '101001'))

    def test_order_observation_at_large_widths(self):
        rng = random.Random(2026091407)
        for width in [1,2,3,8,32,63,64,128,256]:
            for _ in range(30):
                b,a,y,z = [rng.getrandbits(width) for _ in range(4)]; q=(0,0,0,0)
                for i in range(width):
                    c=''.join(str((v>>i)&1) for v in [b,0,0,a,y,z]); q=step(q,c)
                sign = lambda x: (x>0)-(x<0)
                self.assertEqual(q, tuple(sign(x) for x in [a-b,y-b,z-b,z-y]))

    def test_independent_full_raw_input_oracle(self):
        for name in self.sources:
            r = validate(self.sources[name], self.models[name], self.specs['maximum'], max_width=3)
            self.assertEqual(r['inputs'], 2954); self.assertEqual(r['observation_mismatches'], 0)
            if name == 'original': self.assertEqual((r['above_bound'],r['not_maximal']), (0,0))
            elif name == 'plus_one': self.assertGreater(r['above_bound'], 0)
            else:
                self.assertEqual(r['above_bound'], 0); self.assertGreater(r['not_maximal'], 0)

    def test_budget_exhaustion_and_source_change(self):
        p = synthesize(self.sources['original'],self.models['original'],self.specs['maximum'],max_states=1)
        self.assertEqual(p['status'],'budget_exhausted'); self.assertIsNone(p['certificate'])
        with self.assertRaises(ValueError): self.replay('plus_one','maximum',self.certs['original','maximum'])
        forged=copy.deepcopy(self.certs['original','maximum'])
        forged['binding']=System(self.sources['plus_one'],self.models['plus_one'],self.specs['maximum']).binding
        with self.assertRaises(ValueError): self.replay('plus_one','maximum',forged)

    def test_equivalent_guard_and_formal_renaming(self):
        s=self.sources['original'].replace('(value | bit) <= bound','bound >= (bit | value)')
        for old,new in [('bound','limitWord'),('initialValue','seedWord')]: s=s.replace(old,new)
        model=source_producer(s)['certificate']; cert=synthesize(s,model,self.specs['maximum'])['certificate']
        self.assertEqual(check(s,model,self.specs['maximum'],cert)['closed_states'],49)

    def test_fresh_replay_blocks_search_and_native_execution(self):
        script='''
import importlib.abc, json, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (fullname.endswith("producer") or fullname.split(".")[0] in {"subprocess","z3","pysmt","cvc5"}
            or fullname.endswith(("source_validation","property_validation","descending_adapter","source_adapter"))):
            raise RuntimeError("forbidden dependency: "+fullname)
sys.meta_path.insert(0,Block())
from pathlib import Path
from research.observations.property_kernel import check
p=Path(sys.argv[1])
print(json.dumps(check((p/"source.java").read_text(),json.loads((p/"model.json").read_text()),
                      json.loads((p/"spec.json").read_text()),json.loads((p/"proof.json").read_text()))))
'''
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); (p/'spec.json').write_text(json.dumps(self.specs['maximum']))
            for name in ['original','plus_one','strict']:
                (p/'source.java').write_text(self.sources[name]); (p/'model.json').write_text(json.dumps(self.models[name]))
                (p/'proof.json').write_text(json.dumps(self.certs[name,'maximum']))
                for flags in [[],['-O']]:
                    r=subprocess.run([sys.executable,*flags,'-c',script,tmp],cwd=ROOT,text=True,capture_output=True,timeout=20)
                    self.assertEqual(r.returncode,0,r.stderr)
                    self.assertEqual(json.loads(r.stdout)['status'],'certified' if name=='original' else 'refuted')

    def test_cli_refutation_replay_and_file_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); (p/'source.java').write_text(self.sources['plus_one'])
            (p/'model.json').write_text(json.dumps(self.models['plus_one']))
            (p/'spec.json').write_text(json.dumps(self.specs['maximum']))
            args=[str(p/'source.java'),'--source-certificate',str(p/'model.json'),'--spec',str(p/'spec.json'),
                  '--certificate',str(p/'proof.json')]
            def run(command,*extra):
                return subprocess.run([sys.executable,'-O','-m','research.observations.property_cli',command,*args,*extra],
                                      cwd=ROOT,text=True,capture_output=True,timeout=20)
            r=run('derive');self.assertEqual(r.returncode,1,r.stderr);self.assertEqual(json.loads(r.stdout)['status'],'refuted')
            before=(p/'proof.json').read_bytes()
            self.assertEqual(run('check').returncode,1)
            self.assertEqual(run('derive').returncode,3);self.assertEqual((p/'proof.json').read_bytes(),before)
            r=run('derive','--max-states','1');self.assertEqual(r.returncode,2)
            self.assertIsNone(json.loads(r.stdout)['certificate'])


if __name__=='__main__':unittest.main()
