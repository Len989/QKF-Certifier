"""Exact primitive support; no generic formula or Lean-target dependencies."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from research.observations.java_words import extract_mask, pinned_source
from research.observations.run_package import RunError, check_package
from research.observations.run_producer import verify
from research.observations.run_unified_experiment import retained_cases
from research.observations.upstream_transfer import GOALS, UPSTREAM, checked_inputs, goal

# Exact method form at OpenJDK jdk-25-ga, CodeUtil.java, blob 59af250a...;
# the public modifier is outside the existing extracted static method boundary.
MASK = '''static long mask(int bits) {
        assert 0 <= bits && bits <= 64;
        if (bits == 64) {
            return 0xffffffffffffffffL;
        } else {
            return (1L << bits) - 1;
        }
    }'''
ROOT = Path(__file__).resolve().parents[3]


def with_mask(source, replacement=MASK):
    original, _ = extract_mask(source)
    if source.count(original) != 1:
        raise ValueError('one primitive replacement')
    return source.replace(original, replacement)


class UpstreamMaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = pinned_source()
        cls.upstream_form = with_mask(cls.source)
        cls.packages = {}
        for profile, claim in GOALS:
            result, package = verify(cls.upstream_form, goal(profile, claim), profile=profile)
            if result['status'] != 'certified':
                raise AssertionError(result)
            cls.packages[profile, claim] = package

    def test_shim_identity_is_unchanged(self):
        method, identity = extract_mask(self.source)
        self.assertEqual(identity, '5137ee1881d6d0020a0a860095e4db6fbb5ef2ca7a4422c8d296b6b273d116b1')
        self.assertNotEqual(identity, extract_mask(self.upstream_form)[1])
        self.assertIn('bits==64 ? -1L', method)

    def test_exact_original_method_bytes(self):
        method, _ = extract_mask(self.upstream_form)
        self.assertEqual(method, MASK)

    def test_formal_rename_and_layout(self):
        changed = MASK.replace('bits', 'wordWidth').replace('else', '/* layout */ else')
        source = with_mask(self.source, changed)
        self.assertEqual(extract_mask(source)[1], extract_mask(self.upstream_form)[1])

    def test_all_four_fixed_goals(self):
        for (profile, claim), package in self.packages.items():
            result = check_package(self.upstream_form, goal(profile, claim), package)
            self.assertEqual(result['status'], 'certified')
            self.assertEqual(package['schema'], 'qkf-research-package-v1')
            self.assertEqual(package['profile'], profile)

    def test_old_and_new_packages_are_not_interchangeable(self):
        for (profile, claim), package in self.packages.items():
            with self.assertRaises(RunError):
                check_package(self.source, goal(profile, claim), package)

    def test_mutated_source_still_rejected_after_outer_rehash(self):
        package = deepcopy(self.packages['ascending', 'membership'])
        source = self.upstream_form.replace('0xffffffffffffffffL', '0xfffffffffffffffeL')
        package['binding']['source_sha256'] = hashlib.sha256(source.encode()).hexdigest()
        with self.assertRaises(RunError):
            check_package(source, goal('ascending', 'membership'), package)

    def test_unapproved_primitive_changes_fail_closed(self):
        changes = [
            ('width', MASK.replace('bits == 64', 'bits == 63')),
            ('lower guard', MASK.replace('0 <= bits', '1 <= bits')),
            ('upper guard', MASK.replace('bits <= 64', 'bits <= 63')),
            ('disjunction', MASK.replace('&&', '||')),
            ('missing guard', MASK.replace('assert 0 <= bits && bits <= 64;', '')),
            ('wrong all-ones', MASK.replace('0xffffffffffffffffL', '0xfffffffffffffffeL')),
            ('wrong literal type', MASK.replace('1L << bits', '1 << bits')),
            ('wrong subtraction', MASK.replace('- 1;', '- 2;')),
            ('extra effect', MASK.replace('if (bits', 'bits += 1; if (bits')),
            ('early return', MASK.replace('assert', 'return 0; assert')),
        ]
        for label, replacement in changes:
            with self.subTest(label=label), self.assertRaises(ValueError):
                extract_mask(with_mask(self.source, replacement))

    def test_duplicate_primitive_is_rejected(self):
        source = self.upstream_form + '\nclass CodeUtil {' + MASK + '}\n'
        with self.assertRaises(ValueError):
            extract_mask(source)

    def test_missing_dependency_is_not_implicitly_supplied(self):
        source = self.upstream_form.replace('class CodeUtil {', 'class DifferentDependency {')
        for profile, claim in GOALS:
            result, package = verify(source, goal(profile, claim), profile=profile)
            self.assertEqual(result['status'], 'unsupported')
            self.assertIsNone(package)

    def test_all_eighteen_old_verdicts_survive_new_primitive(self):
        for case in retained_cases():
            source = with_mask(case['source'])
            result, package = verify(source, case['spec'], profile=case['profile'])
            self.assertEqual(result['status'], case['expected'], case['id'])
            self.assertEqual(check_package(source, case['spec'], package), result)

    def test_fresh_replay_has_no_deferred_dependencies(self):
        code = '''
import builtins, json, sys
packages = json.load(open(sys.argv[1], encoding="utf-8"))
original = builtins.__import__
def guarded(name, *args, **kwargs):
    parts = name.split(".")
    if any("producer" in p or p.startswith("target_") or p.startswith("composition_")
           or p.startswith("lean_target") or p in {"z3", "cvc5", "subprocess"} for p in parts):
        raise AssertionError("unexpected replay dependency: " + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from research.observations.run_package import check_package
for source, spec, package in packages:
    if check_package(source, spec, package)["status"] != "certified":
        raise AssertionError("unexpected verdict")
print("four independent replays passed")
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'packages.json'
            path.write_text(json.dumps([[self.upstream_form, goal(*key), package]
                                        for key, package in self.packages.items()]))
            for flags in ([], ['-O']):
                result = subprocess.run([sys.executable, *flags, '-c', code, str(path)], cwd=ROOT,
                                        capture_output=True, text=True, timeout=40)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_upstream_inputs_require_exact_pinned_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in UPSTREAM:
                (Path(directory) / (name + '.java')).write_text('class Fake {}')
            with self.assertRaisesRegex(ValueError, 'upstream file identity'):
                checked_inputs(directory)

    def test_only_fixed_goals(self):
        with self.assertRaises(ValueError):
            goal('ascending', 'changes')
        with self.assertRaises(ValueError):
            goal('descending', 'membership')

    @unittest.skipUnless(shutil.which('java'), 'Java source launcher not installed')
    def test_native_mask_every_physical_width(self):
        program = '''public class MaskCheck {
''' + MASK + '''
public static void main(String[] args) {
  for (int w = 0; w <= 64; w++) System.out.println(Long.toUnsignedString(mask(w)));
  for (int w : new int[]{-1, -64, 65, 128, Integer.MIN_VALUE, Integer.MAX_VALUE}) {
    try { mask(w); throw new RuntimeException("missing range assertion"); }
    catch (AssertionError expected) { System.out.println("rejected"); }
  }
}}
'''
        java = shutil.which('java')
        env = os.environ.copy()
        lib = Path(java).resolve().parent.parent / 'lib'
        env['LD_LIBRARY_PATH'] = str(lib) + ':' + str(lib / 'server') + ':' + env.get('LD_LIBRARY_PATH', '')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'MaskCheck.java'
            path.write_text(program)
            result = subprocess.run([java, '-ea', '--source', '17', str(path)],
                                    capture_output=True, text=True, timeout=30, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [str((1 << w) - 1) for w in range(65)] + ['rejected'] * 6)


if __name__ == '__main__':
    unittest.main()
