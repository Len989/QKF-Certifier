"""Audit the published release delta before running unchanged historical guards.

Package CI uses the actual PR tree. Research CI uses a separately identified Git
tree with only the approved publication/CI metadata restored to its old bytes.
Research changes in the PR are retained, so their original guards still apply.
"""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

BASE = "eca90f9252da4480d77c1f8cb4b7062470c57b89"
RELEASE_TREE = "441169fea2a6f17bd2ec393a06e0abcb2b3b257e"
VERSION_PATHS = {"pyproject.toml", "src/qkf_certifier/__init__.py"}
PUBLICATION_FILES = {
    "CHANGELOG.md",
    "CITATION.cff",
    "README.md",
    "README_RU.md",
    "RELEASE_MANIFEST.json",
}
HARNESS_FILES = {
    ".github/workflows/current-research.yml",
    ".github/workflows/observation-inference.yml",
    ".github/workflows/observation-inference-v2.yml",
    ".github/workflows/sdk-cost-contracts.yml",
    ".github/workflows/prepared-context.yml",
    ".github/workflows/direct-emission.yml",
    ".github/workflows/frozen-v3-baseline.yml",
    ".github/workflows/lean-ground.yml",
    ".github/workflows/lean-composition.yml",
}


def git(root, *args, data=None, env=None):
    return subprocess.check_output(["git", "-C", str(root), *args], input=data, env=env)


def entries(root, ref):
    result = {}
    for item in git(root, "ls-tree", "-rz", ref).split(b"\0"):
        if item:
            meta, name = item.split(b"\t", 1)
            mode, kind, blob = meta.decode().split()
            result[name.decode()] = (mode, kind, blob)
    return result


def projection(root, base=BASE, release=RELEASE_TREE, harness=HARNESS_FILES):
    """Create an auditable tree without modifying the checkout or source files."""
    root = Path(root)
    head = git(root, "rev-parse", "HEAD").decode().strip()
    if git(root, "status", "--porcelain", "--untracked-files=no").strip():
        raise ValueError("tracked checkout must be clean")
    old, published, current = (entries(root, ref) for ref in (base, release, head))
    paths = {p for p in old.keys() | published.keys() if old.get(p) != published.get(p)}
    restored = []
    for path in sorted(paths):
        if path in VERSION_PATHS:
            before, after = old.get(path), published.get(path)
            if (
                not before
                or not after
                or before[:2] != ("100644", "blob")
                or after[:2] != before[:2]
            ):
                raise ValueError("version file type/mode changed: " + path)
            raw = git(root, "cat-file", "blob", before[2])
            updated = git(root, "cat-file", "blob", after[2])
            if raw.count(b'"0.2.0a1"') != 1 or raw.replace(b'"0.2.0a1"', b'"0.3.0a1"') != updated:
                raise ValueError("release changes more than a version string: " + path)
        elif path not in PUBLICATION_FILES and not path.startswith(
            ("docs/", "papers/paper_III/", "releases/")
        ):
            raise ValueError("release changes scientific implementation: " + path)
        if current.get(path) not in (old.get(path), published.get(path)):
            raise ValueError("unapproved release metadata: " + path)
        if current.get(path) != old.get(path):
            restored.append(
                {
                    "path": path,
                    "head": current.get(path),
                    "research": old.get(path),
                    "reason": "published release metadata",
                }
            )
    for path in sorted(harness):
        if path not in old or current.get(path, ())[:2] != ("100644", "blob"):
            raise ValueError("CI harness missing or not a regular file: " + path)
        if current[path] != old[path]:
            restored.append(
                {
                    "path": path,
                    "head": current[path],
                    "research": old[path],
                    "reason": "explicit CI harness update",
                }
            )
    with tempfile.TemporaryDirectory() as temporary:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(temporary) / "index")}
        git(root, "read-tree", head, env=env)
        for row in restored:
            path, original = row["path"], row["research"]
            if original is None:
                git(root, "update-index", "--force-remove", "--", path, env=env)
            else:
                mode, kind, blob = original
                if kind != "blob":
                    raise ValueError("unsupported restored entry: " + path)
                git(root, "update-index", "--add", "--cacheinfo", mode, blob, path, env=env)
        tree = git(root, "write-tree", env=env).decode().strip()
    projected = entries(root, tree)
    expected = {row["path"] for row in restored}
    actual = {p for p in current.keys() | projected.keys() if current.get(p) != projected.get(p)}
    if actual != expected:
        raise ValueError("projection changed an unapproved path")
    return {
        "schema": "qkf-release-research-projection-v1",
        "head_commit": head,
        "head_tree": git(root, "rev-parse", head + "^{tree}").decode().strip(),
        "accepted_base": base,
        "published_release_tree": release,
        "research_tree": tree,
        "restored_metadata": restored,
        "scientific_source_unchanged_from_head": True,
        "package_version_tested_on_actual_head_by": "Test and build",
        "scope": "Research code from HEAD, with explicitly recorded archival metadata. Not a release build or historical runtime reproduction.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkout", action="store_true")
    args = parser.parse_args()
    root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel").decode().strip())
    report = projection(root)
    if args.checkout:
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "QKF research CI",
            "GIT_AUTHOR_EMAIL": "qkf-ci@users.noreply.github.com",
            "GIT_COMMITTER_NAME": "QKF research CI",
            "GIT_COMMITTER_EMAIL": "qkf-ci@users.noreply.github.com",
        }
        commit = (
            git(
                root,
                "commit-tree",
                report["research_tree"],
                "-p",
                report["head_commit"],
                data=b"CI-only research projection; see release-compatibility.json for actual head\n",
                env=env,
            )
            .decode()
            .strip()
        )
        git(root, "checkout", "--detach", commit)
        report["research_commit"] = commit
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "head_commit",
                    "head_tree",
                    "research_tree",
                    "scientific_source_unchanged_from_head",
                )
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
