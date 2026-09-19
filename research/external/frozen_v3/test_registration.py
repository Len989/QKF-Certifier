"""Metadata/integrity regressions only; no external acquisition or holdout run."""
from contextlib import contextmanager, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from . import verify as v


class SnapshotTests(unittest.TestCase):
    def test_baseline(self):
        result = v.verify()
        self.assertEqual(result["status"], "baseline_verified")
        self.assertEqual(result["file_count"], 1837)
        self.assertEqual(result["git_tree"], v.BASE_TREE)
        self.assertFalse(result["evaluation_ready"])
        self.assertFalse(result["holdout_executed_by_this_check"])

    def test_git_tree_matches_git_without_repository(self):
        if shutil.which("git") is None:
            self.skipTest("Git cross-check unavailable; byte checks still run")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "z").mkdir()
            (root / "z/a").write_bytes(b"nested\n")
            (root / "z.b").write_bytes(b"sort before z/\n")
            (root / "a").write_bytes(b"a\n")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "core.autocrlf=false",
                            "add", "-A"], check=True)
            expected = subprocess.check_output(["git", "-C", str(root), "write-tree"],
                                               text=True).strip()
            actual = v.snapshot(root)
            shutil.rmtree(root / ".git")
            self.assertEqual(actual, v.snapshot(root))
            self.assertEqual(actual["git_tree"], expected)
            self.assertEqual(actual["file_count"], 3)

    def test_content_mode_addition_deletion_and_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            p = root / "code.py"
            p.write_bytes(b"x=1\n")
            original = v.snapshot(root)
            p.write_bytes(b"x=2\n")
            self.assertNotEqual(original, v.snapshot(root))
            p.write_bytes(b"x=1\n")
            self.assertEqual(original, v.snapshot(root))
            if os.name == "posix":
                p.chmod(0o755)
                self.assertNotEqual(original, v.snapshot(root))
                p.chmod(0o644)
            (root / "shadow.py").write_bytes(b"pass\n")
            self.assertNotEqual(original, v.snapshot(root))
            (root / "shadow.py").unlink()
            (root / "__pycache__").mkdir()
            (root / "__pycache__/code.pyc").write_bytes(b"disposable")
            self.assertEqual(original, v.snapshot(root))
            p.unlink()
            self.assertNotEqual(original, v.snapshot(root))

    @unittest.skipUnless(os.name == "posix", "symlink test requires POSIX")
    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a").write_bytes(b"data")
            (root / "b").symlink_to(root / "a")
            with self.assertRaisesRegex(ValueError, "symlink"):
                v.snapshot(root)

    def test_duplicate_and_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            p = Path(temporary) / "bad.json"
            for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
                p.write_text(text)
                with self.assertRaises(ValueError):
                    v.load(p)

    def test_readiness_gate_exit_two(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = v.main(["--require-corpus"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["reason"], "corpus_not_registered")

    def test_fresh_process_metadata_needs_no_qkf_engine(self):
        script = """
import builtins
original = builtins.__import__
def guard(name, *args, **kwargs):
    if ('producer' in name or name in {'subprocess', 'z3', 'cvc5', 'pysmt'}
        or name.startswith(('research.inference', 'research.unified',
                            'research.observations', 'research.signed_predicates'))):
        raise RuntimeError('metadata must not import proof engine: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guard
from research.external.frozen_v3.verify import main
raise SystemExit(main())
"""
        child = subprocess.run([sys.executable, "-B", "-O", "-c", script], cwd=v.ROOT,
                               text=True, capture_output=True, timeout=30)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertFalse(json.loads(child.stdout)["evaluation_ready"])


class CorruptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name) / "baseline"
        shutil.copytree(v.ROOT, cls.root,
                        ignore=shutil.ignore_patterns(".git", "reproduction", "__pycache__",
                                                     "*.pyc", ".venv", ".pytest_cache"))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @contextmanager
    def changed(self, path, raw):
        p = self.root / path
        original = p.read_bytes() if p.exists() else None
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
        try:
            yield
        finally:
            if original is None:
                p.unlink()
            else:
                p.write_bytes(original)

    def test_delegated_dependency_mutation(self):
        path = "research/observations/run_package.py"
        with self.changed(path, (self.root / path).read_bytes() + b"\n# changed\n"):
            with self.assertRaisesRegex(ValueError, "snapshot changed"):
                v.verify(self.root)

    def test_missing_historical_dependency(self):
        path = self.root / "research/external/frozen_v2/ENGINE.json"
        original = path.read_bytes()
        path.unlink()
        try:
            with self.assertRaisesRegex(ValueError, "snapshot changed"):
                v.verify(self.root)
        finally:
            path.write_bytes(original)

    def test_new_module_shadowing_rejected(self):
        for path in ("json.py", "research/__init__.py",
                     "research/inference/not_registered.py"):
            with self.subTest(path=path), self.changed(path, b"# not in baseline\n"):
                with self.assertRaisesRegex(ValueError, "snapshot changed"):
                    v.verify(self.root)

    def test_historical_claim_map_not_rewritten(self):
        with self.changed("docs/CLAIMS.md", b"rewritten history\n"):
            with self.assertRaisesRegex(ValueError, "snapshot changed"):
                v.verify(self.root)

    def test_protocol_and_roadmap_seals(self):
        for path in (v.PACKAGE + "/PROTOCOL.md", "docs/QKF_ROADMAP_v0.1_RU.md",
                     "docs/CLAIMS_POST_PR25_RU.md", v.PACKAGE + "/ENGINE.json"):
            with self.subTest(path=path), self.changed(path, (self.root / path).read_bytes() + b"\n"):
                with self.assertRaisesRegex(ValueError, "registration seal"):
                    v.verify(self.root)

    def test_unknown_corpus_or_result_rejected(self):
        for name in ("CORPUS.json", "SUMMARY.json", "RESULTS.json", "experiment.py"):
            with self.subTest(name=name), self.changed(v.PACKAGE + "/" + name, b"{}\n"):
                with self.assertRaisesRegex(ValueError, "unexpected registration file"):
                    v.verify(self.root)

    def test_rehashed_tree_substitution_rejected(self):
        ep = v.PACKAGE + "/ENGINE.json"
        rp = v.PACKAGE + "/REGISTRATION.json"
        engine = v.load(self.root / ep)
        engine["snapshot"]["git_tree"] = "0" * 40
        raw = v.canonical(engine)
        registration = v.load(self.root / rp)
        registration["sealed_sha256"][ep] = v.sha256(raw)
        with self.changed(ep, raw), self.changed(rp, v.canonical(registration)):
            with self.assertRaisesRegex(ValueError, "baseline tree anchor"):
                v.verify(self.root)

    def test_false_readiness_rejected(self):
        rp = v.PACKAGE + "/REGISTRATION.json"
        registration = v.load(self.root / rp)
        registration["corpus"] = {"methods": 1}
        with self.changed(rp, v.canonical(registration)):
            with self.assertRaisesRegex(ValueError, "cannot claim a corpus"):
                v.verify(self.root)

    def test_missing_seal_rejected(self):
        rp = v.PACKAGE + "/REGISTRATION.json"
        registration = v.load(self.root / rp)
        registration["sealed_sha256"].pop("docs/CLAIMS_POST_PR25_RU.md")
        with self.changed(rp, v.canonical(registration)):
            with self.assertRaisesRegex(ValueError, "complete registration seals"):
                v.verify(self.root)

    def test_historical_v2_lock_preserved(self):
        lock = v.load(self.root / "research/external/frozen_v2/ENGINE.json")
        self.assertEqual(len(lock["git_blobs"]), 42)
        for path, expected in lock["git_blobs"].items():
            self.assertEqual(v._object("blob", (self.root / path).read_bytes()), expected)


if __name__ == "__main__":
    unittest.main()
