"""Source-region discovery, general arithmetic residuals and proof boundaries."""
import copy
import itertools
import json
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import unittest

from research.observations.ascending_kernel import ALPHABET, Runner, cell, check, check_carrier
from research.observations.ascending_producer import synthesize
from research.observations.ascending_source import extract_region, read_source
from research.observations.ascending_validation import environment, input_word, integer_value, keys, statement, successor
from research.observations.run_ascending_experiment import variants

ROOT = Path(__file__).resolve().parents[3]


class AscendingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = variants()
        cls.certs = {n: synthesize(s)['certificate'] for n, s in cls.sources.items()}

    def test_original_source_claim_and_real_initial_state(self):
        c = self.certs['original']; r = check(self.sources['original'], c)
        self.assertEqual((r['residual_states'], r['observations']['classes']), (3, 2))
        self.assertEqual(c['carrier'][0], {'state': [False, 0], 'parent': None})
        self.assertEqual(r['claim'], 'source_region_model_equivalence')
        self.assertFalse(r['scope']['whole_helper']); self.assertFalse(r['scope']['new_lean_theorem'])
        self.assertEqual(r['scope']['successor_property'], 'not certified by this schema')
        run = Runner(self.sources['original'], c)
        for width in [1, 2, 8, 128]:
            self.assertEqual(run.run(['111'] * width)['outputs'], ['1'] * width)
            self.assertEqual(run.run(['000'] * width)['outputs'], ['0'] * width)
            self.assertEqual(run.run(['011'] * width)['outputs'], ['0'] * width)

    def test_new_offsets_are_discovered_from_addition(self):
        c = self.certs['first_four_bits']; r = check(self.sources['first_four_bits'], c)
        self.assertEqual(r['residual_offsets'], [0, 1, 2])
        self.assertEqual((r['residual_states'], r['observations']['classes']), (4, 4))
        # A different coefficient uses the same compiler and slice rules.
        source = self.sources['first_four_bits'].replace('bit << 2;', 'bit << 3;')
        cert = synthesize(source)['certificate']; result = check(source, cert)
        self.assertIn(4, result['residual_offsets'])

    def test_extra_register_is_erased_by_observations(self):
        c = self.certs['irrelevant_register']; r = check(self.sources['irrelevant_register'], c)
        self.assertEqual((r['residual_states'], r['observations']['classes']), (6, 2))
        self.assertEqual(len(c['source_ir']['register_initial']), 2)

    def test_changed_repair_requires_deeper_question(self):
        c = self.certs['clear_repair']; r = check(self.sources['clear_repair'], c)
        self.assertEqual((r['residual_states'], r['observations']['classes']), (3, 3))
        self.assertEqual(r['observations']['max_witness_length'], 2)
        self.assertTrue(any(p['kind'] == 'pullback' for p in c['observations']['predicates']))

    def test_all_legal_input_columns_and_bounded_successor_oracle(self):
        expected = {''.join(map(str, (m, a, g))) for m, a, g in itertools.product((0, 1), repeat=3) if m <= g <= a}
        self.assertEqual(set(ALPHABET), expected)
        counts = {}
        for name, source in self.sources.items():
            runner = Runner(source, self.certs[name]); region = extract_region(source); bad = 0
            for key in keys(4):
                result = integer_value(region, key)
                bits = runner.run(input_word(key))['outputs']
                self.assertEqual(sum(int(y) << i for i, y in enumerate(bits)), result)
                bad += result != successor(key)
            counts[name] = bad
        self.assertEqual(counts['original'], 0); self.assertEqual(counts['irrelevant_register'], 0)
        for name in ['clear_repair', 'first_or', 'first_four_bits']: self.assertGreater(counts[name], 0)

    def test_slice_identity_with_arbitrary_high_tail_and_low_prefix(self):
        rng = random.Random(202609142)
        for name, source in self.sources.items():
            ir, states = check_carrier(source, self.certs[name]); region = extract_region(source)
            for state, symbol, position in itertools.product(states, ALPHABET, [0, 1, 7, 32, 127]):
                must, may, g = map(int, symbol)
                high = rng.getrandbits(90); low = rng.getrandbits(position)
                original_seed = (2 * high + g) << position
                env = environment(region, position + 100, must << position, may << position, original_seed)
                env[region['word']] = low + ((2 * high + g + state[-1]) << position)
                env[region['loop'][1]] = position
                for i, decl in enumerate(region['declarations']): env[decl[2]] = state[i]
                statement(region['loop'][6], env)
                y, target = cell(ir, state, symbol)
                self.assertEqual(env[region['word']], low + (int(y) << position) + ((high + target[-1]) << (position + 1)))
                self.assertEqual(tuple(env[d[2]] for d in region['declarations']), target[:-1])

    def test_alpha_renaming_equivalent_guards_and_assignment_forms(self):
        source = self.sources['original']
        for name in ['bits', 'mustBeSet', 'mayBeSet', 'newLowerBound', 'incremented', 'optionalBits', 'position', 'bit']:
            source = re.sub(r'\b' + name + r'\b', 'renamed_' + name, source)
        source = source.replace('renamed_newLowerBound += renamed_bit;',
                                'renamed_newLowerBound = renamed_bit + renamed_newLowerBound;')
        source = source.replace('(renamed_bit & renamed_optionalBits) != 0', '0 != (renamed_optionalBits & renamed_bit)')
        cert = synthesize(source)['certificate']; result = check(source, cert)
        self.assertEqual(result['observations']['classes'], 2)
        self.assertEqual(cert['source_ir']['body'], self.certs['original']['source_ir']['body'])

    def test_unsupported_sources_are_rejected(self):
        original = self.sources['original']; region = extract_region(original)['code']
        changes = [region.replace('1L << position', '1 << position'),
                   region.replace('boolean incremented', 'final boolean incremented'),
                   region.replace('position < bits - 1', 'position < bits'),
                   region.replace('position++', 'position--'),
                   region.replace('if (incremented)', 'if (newLowerBound < lowerBound)'),
                   region.replace('newLowerBound += bit;', 'newLowerBound += 1L;'),
                   region.replace('incremented = true;', 'incremented = unknown;'),
                   region.replace('newLowerBound |= bit;', 'newLowerBound |= bit << 1;')]
        for changed in changes:
            with self.subTest(change=changed):
                with self.assertRaises(ValueError): read_source(original.replace(region, changed))
        primitive = original.replace('(1L<<bits)-1;', '(1L<<bits)-2;')
        self.assertTrue(primitive != original, 'mutation must change the bound primitive')
        with self.assertRaises(ValueError): read_source(primitive)

    def test_certificate_mutation_rejection(self):
        changes = {
            'omit': lambda c:c['carrier'].pop(),
            'duplicate': lambda c:c['carrier'].append(copy.deepcopy(c['carrier'][-1])),
            'empty': lambda c:c.update(carrier=[]),
            'bool_offset': lambda c:c['carrier'][0]['state'].__setitem__(-1, False),
            'int_register': lambda c:c['carrier'][0]['state'].__setitem__(0, 0),
            'negative': lambda c:c['carrier'][0]['state'].__setitem__(-1, -1),
            'virtual_initial': lambda c:c['carrier'][0]['state'].__setitem__(-1, 1),
            'cycle': lambda c:c['carrier'][1]['parent'].__setitem__(0, 1),
            'wrong_parent': lambda c:c['carrier'][1]['parent'].__setitem__(1, '000'),
            'illegal_column': lambda c:c['carrier'][1]['parent'].__setitem__(1, '100'),
            'bad_rule': lambda c:c['source_ir']['rules'].append('trust me'),
            'bad_profile': lambda c:c['source_ir']['profile'].update(answer='full signed word'),
            'bad_source': lambda c:c['source_ir'].update(source_sha256='0' * 64),
            'bad_partition': lambda c:c['observations']['blocks'][0].pop(),
            'bad_row': lambda c:c['observations']['rows'][0]['supplied'][0].__setitem__(1, 99),
            'bad_cell': lambda c:c['observations']['cells'][0].update(output='1'),
            'extra': lambda c:c.update(verified=True),
        }
        for name, mutate in changes.items():
            with self.subTest(name=name):
                cert = copy.deepcopy(self.certs['original']); mutate(cert)
                with self.assertRaises(ValueError): check(self.sources['original'], cert)

    def test_source_substitution_and_budget_do_not_invent_proof(self):
        for options in [{'max_states': 1}, {'max_offset': 0}, {'max_observations': 0}]:
            result = synthesize(self.sources['original'], **options)
            self.assertEqual(result['status'], 'budget_exhausted'); self.assertIsNone(result['certificate'])
        c = copy.deepcopy(self.certs['original'])
        c['source_ir'] = read_source(self.sources['clear_repair'])
        with self.assertRaises(ValueError): check(self.sources['clear_repair'], c)
        with self.assertRaises(ValueError): Runner(self.sources['original'], self.certs['original']).run(['100'])

    def test_fresh_replay_without_producers_old_models_or_native_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory); (d / 'source.java').write_text(self.sources['first_four_bits'])
            (d / 'certificate.json').write_text(json.dumps(self.certs['first_four_bits']))
            script = '''
import importlib.abc, json, pathlib, sys
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if any(x in fullname for x in ['producer','source_adapter','descending_adapter','graal','validation','subprocess','z3','pysmt','cvc5']):
   raise RuntimeError('blocked import: '+fullname)
sys.meta_path.insert(0, Block())
from research.observations.ascending_kernel import check
d=pathlib.Path(sys.argv[1])
print(json.dumps(check((d/'source.java').read_text(),json.loads((d/'certificate.json').read_text()))))
'''
            for flags in [[], ['-O']]:
                r = subprocess.run([sys.executable, *flags, '-c', script, directory], cwd=ROOT,
                                   capture_output=True, text=True, timeout=30)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(json.loads(r.stdout)['residual_offsets'], [0, 1, 2])

    def test_cli_check_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory); source = d / 'source.java'; cert = d / 'cert.json'
            source.write_text(self.sources['original']); cert.write_text(json.dumps(self.certs['original']))
            before = cert.read_bytes()
            def run(command):
                return subprocess.run([sys.executable, '-O', '-m', 'research.observations.ascending_cli',
                                       command, str(source), str(cert)], cwd=ROOT, capture_output=True, text=True, timeout=30)
            self.assertEqual(run('check').returncode, 0)
            self.assertEqual(run('derive').returncode, 1); self.assertEqual(cert.read_bytes(), before)
            cert.write_text('{}'); self.assertEqual(run('check').returncode, 1)


if __name__ == '__main__': unittest.main()
