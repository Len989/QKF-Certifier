import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=None):
    p = subprocess.run(
        [sys.executable, "-m", "qkf_certifier", *map(str, args)],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return p, json.loads(p.stdout) if "--json" in args else p.stdout


def test_verify_and_replay_outside_checkout(tmp_path):
    source = ROOT / "examples/ntmy/xor.mlir"
    helper = "meet=" + str(ROOT / "examples/ntmy/meet.mlir")
    cert = tmp_path / "proof.json"
    p, r = run(
        "verify",
        source,
        "--target",
        "xor",
        "--helper",
        helper,
        "--certificate",
        cert,
        "--json",
        cwd=tmp_path,
    )
    assert p.returncode == 0 and r["status"] == "certified" and cert.exists()
    p, r = run(
        "check",
        source,
        "--target",
        "xor",
        "--helper",
        helper,
        "--certificate",
        cert,
        "--json",
        cwd=tmp_path,
    )
    assert p.returncode == 0 and r["optimal"]
    cert.write_text('{"schema":null}')
    p, r = run(
        "check", source, "--target", "xor", "--helper", helper, "--certificate", cert, "--json"
    )
    assert p.returncode == 3 and r["status"] == "invalid_certificate"


def test_input_and_output_errors(tmp_path):
    p, r = run("verify", tmp_path / "missing.mlir", "--target", "and", "--json")
    assert p.returncode == 64 and r["status"] == "input_error"
    source = tmp_path / "and.mlir"
    source.write_bytes((ROOT / "examples/ntmy/and.mlir").read_bytes())
    before = source.read_bytes()
    p, r = run("verify", source, "--target", "and", "--certificate", source, "--force", "--json")
    assert p.returncode == 64 and source.read_bytes() == before
    out = tmp_path / "existing.json"
    out.write_text("keep")
    p, r = run("verify", source, "--target", "and", "--certificate", out, "--json")
    assert p.returncode == 64 and out.read_text() == "keep"
    p, r = run("verify", source, "--target", "and", "--certificate", out, "--force", "--json")
    assert p.returncode == 0 and json.loads(out.read_text())["target"] == "and"


def test_unsupported_and_unsound_exit_codes(tmp_path):
    source = ROOT / "examples/ntmy/and.mlir"
    p, r = run("verify", source, "--target", "add", "--json")
    assert p.returncode == 2
    changed = tmp_path / "wrong.mlir"
    changed.write_text(source.read_text().replace("func.return %10", "func.return %arg0"))
    p, r = run("verify", changed, "--target", "and", "--json")
    assert p.returncode == 1 and r["witness"]["width"] == 1


def test_batch_aggregate_and_relative_paths(tmp_path):
    (tmp_path / "and.mlir").write_bytes((ROOT / "examples/ntmy/and.mlir").read_bytes())
    manifest = tmp_path / "batch.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "qkf-batch-v1",
                "items": [
                    {"id": "good", "source": "and.mlir", "target": "and"},
                    {"id": "deferred", "source": "and.mlir", "target": "add"},
                ],
            }
        )
    )
    p, r = run("batch", manifest, "--json", cwd=tmp_path)
    assert p.returncode == 2 and [x["status"] for x in r["items"]] == [
        "certified",
        "fallback_required",
    ]


def test_cli_normalization_is_explicit(tmp_path):
    source = ROOT / "examples/fallback_add.mlir"
    out = tmp_path / "normal.json"
    p, r = run("normalize", source, "--certificate", out, "--json")
    assert p.returncode == 0 and r["status"] == "normalized" and not r["all_positive_widths"]
    p, r = run("check", source, "--normalization-only", "--certificate", out, "--json")
    assert p.returncode == 0 and r["normalization_verified"]
    p, r = run("check", source, "--target", "and", "--certificate", out, "--json")
    assert p.returncode == 3


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["verify"],
        ["verify", "x", "--json"],
        ["check", "x", "--certificate", "x", "--json"],
        ["verify", "x", "--target", "and", "--unknown", "--json"],
    ],
)
def test_usage_errors_are_nonzero(args):
    p, _ = run(*args)
    assert p.returncode == 64


def test_crlf_hash_is_bound_to_exact_bytes(tmp_path):
    import hashlib

    raw = (ROOT / "examples/ntmy/and.mlir").read_bytes().replace(b"\n", b"\r\n")
    source = tmp_path / "and.mlir"
    source.write_bytes(raw)
    p, r = run("verify", source, "--target", "and", "--json")
    assert p.returncode == 0
    assert r["source_hashes"]["program"] == hashlib.sha256(raw).hexdigest()
