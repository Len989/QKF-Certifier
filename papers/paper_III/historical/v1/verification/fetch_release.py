#!/usr/bin/env python3
"""Retrieve or check the immutable public source identified by CODE_VERSION.json.

Existing paths are only checked; they are never reset, cleaned, or overwritten.
Uses Python 3.10+ and git. A new checkout needs public network access.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "CODE_VERSION.json").read_text())
    repo = args.destination.resolve()
    if not repo.exists():
        if args.check_only:
            raise SystemExit("Checkout does not exist")
        repo.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", "--branch",
                        manifest["software"]["tag"],
                        manifest["software"]["repository"], str(repo)], check=True)
    actual = run("git", "rev-parse", "HEAD", cwd=repo)
    if actual != manifest["software"]["commit"]:
        raise SystemExit("Commit mismatch; existing checkout left unchanged: " + actual)
    if run("git", "status", "--porcelain", "--untracked-files=no", cwd=repo):
        raise SystemExit("Tracked files are modified; checkout left unchanged")
    for name, expected in manifest["tracked_file_sha256"].items():
        path = repo / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit("Source hash mismatch: " + name)
    print("PASS: pinned commit and", len(manifest["tracked_file_sha256"]), "tracked file hashes")


if __name__ == "__main__":
    main()
