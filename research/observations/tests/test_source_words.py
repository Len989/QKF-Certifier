"""Symbolic integer/source checks, independent concrete values and chain replay."""
import copy
import json
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import unittest

from research.observations.context_checker import check as check_context
from research.observations.context_producer import synthesize as context_producer
from research.observations.java_words import pinned_source, read_source
from research.observations.source_factor import Runner, check, synthesize
from research.observations.source_validation import validate
from research.observations.word_kernel import check_word, compiled_model, locate
from research.observations.word_producer import synthesize as word_producer

ROOT = Path(__file__).resolve().parents[3]
MARKER = '(value | bit) <= bound'


def changed(comparison):
    source = pinned_source()
    if source.count(MARKER) != 1: raise RuntimeError('pinned decision count')
    return source.replace(MARKER, comparison)


def candidate(source):
    p = synthesize(source)
    if p['status'] != 'candidate': raise ValueError(p)
    check(source, p['certificate'])
    return p['certificate']


class SourceWordTests(unittest.TestCase):
    def test_vocabulary_changes_with_source_offset(self):
        for offset, values, actions, residuals, classes in [(0, 3, 3, 15, 10), (1, 4, 6, 27, 13), (3, 6, 13, 62, 20)]:
            source = changed(f'(value | bit) <= bound + {offset}') if offset else pinned_source()
            cert = candidate(source); result = check(source, cert)
            self.assertEqual((result['word']['context_values'], result['word']['suffix_actions']), (values, actions))
            self.assertEqual((result['factor']['residual_states'], result['factor']['classes']), (residuals, classes))
            self.assertEqual(validate(source, cert, max_width=3)['mismatches'], 0)

    def test_shared_input_identity_is_extracted(self):
        source = changed('(value | bit) <= initialValue'); cert = candidate(source)
        ir = cert['word']['source_ir']; wiring = ir['wiring']
        self.assertEqual(ir['comparison_word'], 'arg4')
        self.assertEqual(wiring['lower_control']['left'], wiring['lower_control']['right'])
        self.assertTrue(all(c['symbol'][0] == c['symbol'][2] for c in ir['columns']))
        self.assertEqual(len(cert['word']['monoid']), 1)
        self.assertEqual(check(source, cert)['factor']['classes'], 2)
        self.assertEqual(validate(source, cert, max_width=4)['mismatches'], 0)

    def test_formal_local_renaming_and_equivalent_guards(self):
        source = pinned_source(); original = candidate(source)
        expected = compiled_model(source, original['word'])['rows']
        rng = random.Random(2026091401)
        names = ['bits', 'bound', 'mustBeSet', 'mayBeSet', 'initialValue', 'optionalBits', 'value', 'position', 'bit']
        for _ in range(12):
            labels = [f'local_{i}' for i in range(len(names))]; rng.shuffle(labels)
            mapping = dict(zip(names, labels))
            renamed = re.sub(r'\b(' + '|'.join(names) + r')\b', lambda m: mapping[m.group()], source)
            cert = candidate(renamed)
            self.assertEqual(compiled_model(renamed, cert['word'])['rows'], expected)
        for expression in ['bound >= (bit | value)', '!((value | bit) > bound)', '((value | bit) + 1) <= (bound + 1)']:
            source = changed(expression); cert = candidate(source)
            self.assertEqual(compiled_model(source, cert['word'])['rows'], expected)

    def test_symbolic_actions_against_large_integers(self):
        integers = list(range(-257, 258)) + [-(10 ** 80), -(10 ** 40), 10 ** 40, 10 ** 80]
        for op in ['<', '<=', '==', '!=', '>', '>=']:
            for offset in [-3, -1, 0, 1, 3]:
                expression = f'(value | bit) {op} (bound + {offset})' if offset >= 0 else f'(value | bit) {op} (bound - {-offset})'
                source = changed(expression); p = word_producer(source)
                self.assertEqual(p['status'], 'candidate')
                cert = p['certificate']; check_word(source, cert)
                parts = cert['intervals']
                for d in integers:
                    q = locate(parts, d)
                    expected = {'<': d < offset, '<=': d <= offset, '==': d == offset,
                                '!=': d != offset, '>': d > offset, '>=': d >= offset}[op]
                    self.assertEqual(cert['consumer'][q], [expected])
                    for action in cert['actions']:
                        self.assertEqual(action['targets'][q], locate(parts, 2 * d + action['delta']))

    def test_atomic_context_rows_match_complete_replay(self):
        for offset in [0, 1, 3]:
            source = changed(f'(value | bit) <= bound + {offset}')
            word = word_producer(source)['certificate']; model = compiled_model(source, word)
            full = context_producer(model)['certificate']
            compact = context_producer(model, row_encoding='atomic')['certificate']
            check_context(model, compact)
            for field in ['states', 'cells', 'gap', 'initial']:
                self.assertEqual(full[field], compact[field])
            self.assertTrue(all('table' not in r for r in compact['rows']))

    def test_source_changes_and_rehashed_old_vocabulary_rejected(self):
        source = pinned_source(); cert = candidate(source)
        new = changed('(value | bit) <= bound + 1')
        with self.assertRaises(ValueError): check(new, cert)
        cert['word']['source_ir'] = read_source(new)
        with self.assertRaises(ValueError): check_word(new, cert['word'])

    def test_unsupported_source_and_callee_changes(self):
        source = pinned_source()
        variants = [
            source.replace('position--', 'position++'),
            source.replace('1L << position;', '1L << (position + 1);'),
            source.replace('1L << position;', '1 << position;'),
            source.replace(MARKER, '(value | bit) <= bound + 010'),
            source.replace('value |= bit;', 'value += bit;'),
            source.replace('return value;', 'return bound;'),
            source.replace(MARKER, '(initialValue | bit) <= bound'),
            source.replace(MARKER, '(value | bit) <= bound && (value | bit) <= initialValue'),
            source.replace('value |= bit;', 'value |= bit; value |= 2L;'),
            source.replace('(bit & optionalBits) != 0 && ', ''),
            source.replace('return bits==64 ? -1L : (1L<<bits)-1;', 'return 0L;'),
        ]
        for i, s in enumerate(variants):
            with self.subTest(i=i):
                self.assertNotEqual(source, s)
                with self.assertRaises(ValueError): synthesize(s)
        # A declaration hidden in a comment is not a second source helper.
        comment = '\n/* private static long setOptionalBits(int x) { return 0; } */\n'
        self.assertEqual(candidate(source + comment)['word']['actions'], candidate(source)['word']['actions'])

    def test_word_and_composed_certificate_mutations(self):
        source = pinned_source(); original = candidate(source)
        mutations = {
            'source_hash': lambda c: c['word']['source_ir'].update(source_sha256='0' * 64),
            'fresh_context': lambda c: c['word']['source_ir']['wiring']['through'].update(higher=['fresh']),
            'lost_lower_identity': lambda c: c['word']['source_ir']['wiring']['lower_control'].update(left=['fresh']),
            'unbound_callee': lambda c: c['word']['source_ir'].update(primitive_bindings={}),
            'bool_offset': lambda c: c['word']['source_ir']['tests'][0].update(offset=False),
            'missing_question': lambda c: c['word']['questions'].pop(),
            'pullback': lambda c: c['word']['questions'][1].update(cut=-2),
            'cycle': lambda c: c['word']['questions'][1].update(parent=1),
            'interval': lambda c: c['word']['intervals'][0].update(lower=-100),
            'sample_only_target': lambda c: c['word']['actions'][0]['targets'].__setitem__(0, 1),
            'missing_action': lambda c: c['word']['actions'].pop(),
            'origin': lambda c: c['word'].update(origin=0),
            'consumer': lambda c: c['word']['consumer'][0].__setitem__(0, False),
            'identity': lambda c: c['word']['monoid'][0]['map'].__setitem__(0, 1),
            'monoid_parent': lambda c: c['word']['monoid'][1]['parent'].update(state=1),
            'composition': lambda c: c['word']['composition'][0].update(next=0),
            'missing_composition': lambda c: c['word']['composition'].pop(),
            'row_projection': lambda c: c['factor']['context']['rows'][0].update(kernel_projection=0),
            'factor_binding': lambda c: c['factor'].update(context_model_sha256='0' * 64),
            'factor_initial': lambda c: c['factor']['factor'].update(initial=False),
            'unknown_field': lambda c: c.update(trust_me=True),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                cert = copy.deepcopy(original); mutate(cert)
                with self.assertRaises(ValueError): check(source, cert)

    def test_budget_failure_is_explicit(self):
        for budgets in [{'max_contexts': 2}, {'max_actions': 2}]:
            p = synthesize(pinned_source(), **budgets)
            self.assertEqual(p['status'], 'budget_exhausted'); self.assertIsNone(p['certificate'])
        p = synthesize(changed('(value | bit) <= bound + 100000'))
        self.assertEqual(p['status'], 'budget_exhausted'); self.assertIsNone(p['certificate'])

    def test_fresh_replay_needs_neither_old_adapters_nor_java(self):
        code = '''
import importlib.abc, json, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (fullname.endswith("producer") or fullname.split(".")[0] in {"subprocess", "z3", "pysmt", "cvc5"}
            or fullname in {"research.observations.descending_adapter", "research.observations.source_adapter"}):
            raise RuntimeError("forbidden replay dependency: " + fullname)
sys.meta_path.insert(0, Block())
from pathlib import Path
from research.observations.java_words import pinned_source
from research.observations.source_factor import check
print(json.dumps(check(pinned_source(), json.loads(Path(sys.argv[1]).read_text()))))
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'certificate.json'; cert = candidate(pinned_source()); path.write_text(json.dumps(cert))
            for flags in [[], ['-O']]:
                r = subprocess.run([sys.executable, *flags, '-c', code, str(path)], cwd=ROOT,
                                   capture_output=True, text=True, timeout=20)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(json.loads(r.stdout)['factor']['classes'], 10)
            cert['word']['source_ir']['tests'][0]['offset'] = False; path.write_text(json.dumps(cert))
            r = subprocess.run([sys.executable, '-O', '-c', code, str(path)], cwd=ROOT,
                               capture_output=True, text=True, timeout=20)
            self.assertNotEqual(r.returncode, 0)


if __name__ == '__main__': unittest.main()
