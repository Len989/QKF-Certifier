"""Verify baseline bytes and the pre-corpus registration, without importing QKF.

The lock conservatively covers the entire accepted repository snapshot, including
all transitive engine imports, delegated routes, data, tests and historical code.
It is not a claim that all locked files are needed by every proof. Git tree hashes
are recomputed from bytes and modes; no Git executable or .git directory is needed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import stat

BASE_COMMIT = "c8c7b4eeaf848d31c8c324a4316ffec8aac81cda"
BASE_TREE = "4838b8badbb3a56f8a7d2a197ce6c0d3d6b3a77d"
ROOT = Path(__file__).resolve().parents[3]
PACKAGE = "research/external/frozen_v3"
ADDITIONS = frozenset({
    PACKAGE,
    "docs/QKF_ROADMAP_v0.1_RU.md",
    "docs/CLAIMS_POST_PR25_RU.md",
    ".github/workflows/frozen-v3-baseline.yml",
})
# Only disposable caches/output areas absent from the accepted snapshot.
ROOT_OUTPUTS = frozenset({".git", "reproduction", ".venv", ".pytest_cache",
                          ".ruff_cache", ".hypothesis", "build", "dist"})


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _object(kind, raw):
    return hashlib.sha1(kind.encode("ascii") + b" " + str(len(raw)).encode("ascii")
                        + b"\0" + raw).hexdigest()


def snapshot(root):
    """Full baseline Merkle identity; detect changes, deletions and additions.

    Symlinks are rejected: the baseline has none. Cache exclusions are not a
    sandbox. Evaluation must use a clean isolated checkout, not execute caches.
    """
    root = Path(root)
    records = []

    def walk(directory, relative=""):
        children = []
        for item in directory.iterdir():
            name = item.name
            path = name if not relative else relative + "/" + name
            if path in ADDITIONS or (not relative and name in ROOT_OUTPUTS):
                continue
            if name == "__pycache__" or name.endswith((".pyc", ".pyo")):
                continue
            mode = item.lstat().st_mode
            require(not stat.S_ISLNK(mode), "symlink in baseline: " + path)
            if stat.S_ISDIR(mode):
                tree_hash, nonempty = walk(item, path)
                if nonempty:  # Git does not store empty directories.
                    children.append((name + "/", b"40000", name, tree_hash))
            else:
                require(stat.S_ISREG(mode), "non-regular baseline file: " + path)
                raw = item.read_bytes()
                git_mode = "100755" if mode & 0o111 else "100644"
                blob = _object("blob", raw)
                records.append({"path": path, "mode": git_mode,
                                "size": len(raw), "sha256": sha256(raw)})
                children.append((name, git_mode.encode("ascii"), name, blob))
        children.sort(key=lambda row: row[0].encode("utf-8"))
        raw = b"".join(mode + b" " + name.encode("utf-8") + b"\0" + bytes.fromhex(obj)
                       for _, mode, name, obj in children)
        return _object("tree", raw), bool(children)

    tree_hash, _ = walk(root)
    records.sort(key=lambda row: row["path"].encode("utf-8"))
    return {"git_tree": tree_hash, "file_count": len(records),
            "total_bytes": sum(row["size"] for row in records),
            "inventory_sha256": sha256(canonical(records))}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def load(path):
    def no_constant(value):
        raise ValueError("non-finite JSON value: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=_unique, parse_constant=no_constant)


def verify_engine(root=ROOT):
    root = Path(root)
    engine = load(root / PACKAGE / "ENGINE.json")
    require(engine["schema"] == "qkf-frozen-v3-engine-lock-v1", "engine lock schema")
    require(engine["baseline_commit"] == BASE_COMMIT, "baseline commit")
    require(engine["snapshot"]["git_tree"] == BASE_TREE, "baseline tree anchor")
    require(engine["snapshot"]["file_count"] == 1837, "baseline file count")
    require(engine["scope"] == "entire-baseline-snapshot", "conservative freeze scope")
    require(engine["excluded_additions"] == sorted(ADDITIONS), "freeze exclusions")
    actual = snapshot(root)
    require(actual == engine["snapshot"], "baseline snapshot changed: " + str(actual))
    return actual


def verify_seals(root=ROOT):
    root = Path(root)
    registration = load(root / PACKAGE / "REGISTRATION.json")
    require(set(registration) == {"schema", "phase", "baseline_commit", "corpus",
                                 "first_holdout_execution", "sealed_sha256"},
            "registration fields")
    require(registration["schema"] == "qkf-frozen-v3-registration-v1", "registration schema")
    require(registration["baseline_commit"] == BASE_COMMIT, "registration baseline")
    require(registration["phase"] == "engine_and_protocol_frozen", "registration phase")
    require(registration["corpus"] is None and registration["first_holdout_execution"] is None,
            "PR26 cannot claim a corpus or holdout execution")
    paths = {PACKAGE + "/ENGINE.json", PACKAGE + "/PROTOCOL.md",
             "docs/QKF_ROADMAP_v0.1_RU.md", "docs/CLAIMS_POST_PR25_RU.md"}
    require(set(registration["sealed_sha256"]) == paths, "complete registration seals")
    for path, expected in registration["sealed_sha256"].items():
        require(sha256((root / path).read_bytes()) == expected, "registration seal: " + path)
    allowed = {"__init__.py", "ENGINE.json", "PROTOCOL.md", "REGISTRATION.json",
               "verify.py", "test_registration.py", "__pycache__", "run27"}
    require({p.name for p in (root / PACKAGE).iterdir()} <= allowed,
            "unexpected registration file; corpus/results must not be added silently")
    # Run27 is an explicitly versioned preparation/evaluation stage. This
    # historical PR26 verifier still never declares its corpus ready. Run27's
    # independent seals and execution gate are checked by its own verifier.
    stage = root / PACKAGE / "run27"
    if stage.exists():
        acquisition = load(stage / "ACQUISITION.json")
        require(acquisition["schema"] == "qkf-frozen-v3-acquisition-v1"
                and acquisition["baseline_commit"] == BASE_COMMIT
                and acquisition["protocol_sha256"] == registration["sealed_sha256"][PACKAGE + "/PROTOCOL.md"],
                "run27 acquisition anchor")
    return registration


def verify(root=ROOT):
    registration = verify_seals(root)
    identity = verify_engine(root)
    return {"schema": "qkf-frozen-v3-preflight-v1", "status": "baseline_verified",
            "baseline_commit": BASE_COMMIT, **identity,
            "phase": registration["phase"], "evaluation_ready": False,
            "reason": "corpus_not_registered", "holdout_executed_by_this_check": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--require-corpus", action="store_true",
                        help="fail closed: PR26 has no registered corpus")
    args = parser.parse_args(argv)
    try:
        result = verify(args.root)
        code = 2 if args.require_corpus else 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        result = {"schema": "qkf-frozen-v3-preflight-v1", "status": "invalid_baseline",
                  "evaluation_ready": False, "error": str(exc)}
        code = 1
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
