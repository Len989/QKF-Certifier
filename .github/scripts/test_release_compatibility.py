"""Negative controls for the boundary between release and scientific changes."""

import tempfile
import unittest
from pathlib import Path

from release_compatibility import entries, git, projection


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        git(self.root, "init", "--quiet")
        git(self.root, "config", "user.name", "Test")
        git(self.root, "config", "user.email", "test@example.invalid")
        for path, text in {
            "pyproject.toml": 'version = "0.2.0a1"\n',
            "src/qkf_certifier/__init__.py": '__version__ = "0.2.0a1"\n',
            "research/checker.py": "def check(): return True\n",
            "README.md": "Original documentation\n",
            ".github/workflows/current-research.yml": "original harness\n",
        }.items():
            self.write(path, text)
        self.base = self.commit()
        self.write("pyproject.toml", 'version = "0.3.0a1"\n')
        self.write("src/qkf_certifier/__init__.py", '__version__ = "0.3.0a1"\n')
        self.write("README.md", "Published release\n")
        self.write("docs/release.md", "Release notes\n")
        self.release = self.commit()
        self.harness = {".github/workflows/current-research.yml"}

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def commit(self):
        git(self.root, "add", ".")
        git(self.root, "commit", "--quiet", "-m", "fixture")
        return git(self.root, "rev-parse", "HEAD").decode().strip()

    def audit(self):
        return projection(self.root, self.base, self.release, self.harness)

    def test_exact_release_restores_metadata_without_modifying_checkout(self):
        result = self.audit()
        self.assertEqual(entries(self.root, result["research_tree"]), entries(self.root, self.base))
        self.assertEqual(git(self.root, "rev-parse", "HEAD").decode().strip(), self.release)
        self.assertIn("0.3.0a1", (self.root / "pyproject.toml").read_text())

    def test_existing_scientific_mutation_is_retained_for_original_guards(self):
        self.write("research/checker.py", "def check(): return False\n")
        head = self.commit()
        tree = self.audit()["research_tree"]
        self.assertEqual(
            entries(self.root, tree)["research/checker.py"],
            entries(self.root, head)["research/checker.py"],
        )
        self.assertNotEqual(
            entries(self.root, tree)["research/checker.py"],
            entries(self.root, self.base)["research/checker.py"],
        )

    def test_scientific_deletion_and_addition_are_not_hidden(self):
        (self.root / "research/checker.py").unlink()
        self.write("research/new.py", "new = True\n")
        self.commit()
        tree = entries(self.root, self.audit()["research_tree"])
        self.assertNotIn("research/checker.py", tree)
        self.assertIn("research/new.py", tree)

    def test_unapproved_version_or_runtime_logic_is_rejected(self):
        self.write("src/qkf_certifier/__init__.py", '__version__ = "0.3.0a1"\nexec("changed")\n')
        self.commit()
        with self.assertRaisesRegex(ValueError, "unapproved release metadata"):
            self.audit()

    def test_unapproved_documentation_is_not_silently_restored(self):
        self.write("README.md", "An unreviewed change\n")
        self.commit()
        with self.assertRaisesRegex(ValueError, "unapproved release metadata"):
            self.audit()

    def test_version_file_mode_change_is_rejected(self):
        git(self.root, "update-index", "--chmod=+x", "pyproject.toml")
        git(self.root, "commit", "--quiet", "-m", "mode change")
        # Match the checkout to its new index mode before checking the policy.
        (self.root / "pyproject.toml").chmod(0o755)
        with self.assertRaisesRegex(ValueError, "unapproved release metadata"):
            self.audit()

    def test_release_reference_cannot_authorize_scientific_changes(self):
        self.write("research/checker.py", "altered = True\n")
        self.release = self.commit()
        with self.assertRaisesRegex(ValueError, "release changes scientific implementation"):
            self.audit()

    def test_release_reference_cannot_authorize_runtime_logic(self):
        self.write("src/qkf_certifier/__init__.py", '__version__ = "0.3.0a1"\nextra = True\n')
        self.release = self.commit()
        with self.assertRaisesRegex(ValueError, "more than a version string"):
            self.audit()

    def test_only_explicit_harness_paths_are_restored(self):
        self.write(".github/workflows/current-research.yml", "new harness\n")
        self.write(".github/workflows/another.yml", "new workflow\n")
        self.commit()
        tree = entries(self.root, self.audit()["research_tree"])
        self.assertEqual(
            tree[".github/workflows/current-research.yml"],
            entries(self.root, self.base)[".github/workflows/current-research.yml"],
        )
        self.assertIn(".github/workflows/another.yml", tree)

    def test_dirty_tracked_checkout_is_rejected(self):
        self.write("research/checker.py", "dirty = True\n")
        with self.assertRaisesRegex(ValueError, "must be clean"):
            self.audit()


if __name__ == "__main__":
    unittest.main()
