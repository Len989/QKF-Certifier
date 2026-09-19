"""Minimal frozen-source provenance checks without native/subprocess dependencies."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "research/external/frozen_v1"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def corpus():
    return json.loads((FROZEN / "CORPUS.json").read_text(encoding="utf-8"))


def check_blob(raw, identity):
    require(type(raw) is bytes and len(raw) <= corpus()["budget"]["source_bytes_limit"], "source size")
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    require(actual == identity["blob"], "original Git blob differs: " + identity["path"])
    raw.decode("utf-8")
    return {**identity, "sha256": _sha(raw), "bytes": len(raw), "git_blob_verified": True}


def check_engine():
    expected = json.loads((FROZEN / "ENGINE.json").read_text(encoding="utf-8"))
    actual = {
        str(p.relative_to(ROOT)): _sha(p.read_bytes())
        for prefix in expected["roots"]
        for p in sorted((ROOT / prefix).rglob("*" + expected["suffix"]))
        if expected["exclude_directory"] not in p.parts and "__pycache__" not in p.parts
    }
    require(len(actual) == expected["file_count"], "frozen engine file set changed")
    require(_sha(_canonical(actual)) == expected["sha256"], "frozen engine bytes changed")
    return actual
