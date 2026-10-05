"""Bounded-memory producer, freeze verification, capture, then independent cold audit."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
ENGINES = ["minimal", "minimal_pressure", "ordinary", "staged", "reference"]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(65536):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def sources():
    paths = sorted(ROOT.glob("*.py")) + sorted((ROOT / "vendor").rglob("*.py"))
    paths += [ROOT / "PROTOCOL_RU.md", ROOT / "HISTORY_RU.md", ROOT.parents[2] / ".github/workflows/qkf-ai-run26.yml"]
    return {str(p.relative_to(ROOT.parents[2])): digest(p) for p in paths}


def freeze():
    hashes = sources()
    body = {"schema": "qkf.run26.freeze.v1", "source_sha256": hashes, "execution_order": specs()}
    body["protocol_sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    write_json(ROOT / "PROTOCOL_FREEZE.json", body)
    return body


def verify_freeze():
    saved = json.loads((ROOT / "PROTOCOL_FREEZE.json").read_text())
    unsigned = {k: v for k, v in saved.items() if k != "protocol_sha256"}
    sha = hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if sources() != saved["source_sha256"] or sha != saved["protocol_sha256"] or specs() != saved["execution_order"]:
        raise RuntimeError("source/protocol freeze mismatch")
    return saved


def specs():
    result = []
    for repeat in range(2):
        for n in [100000, 300000]:
            rotation = (repeat + (n // 100000)) % len(ENGINES)
            order = ENGINES[rotation:] + ENGINES[:rotation]
            for engine in order:
                result.append({"id": f"normal_r{repeat}_n{n}_{engine}", "engine": engine, "n": n, "repeat": repeat, "kill_at": "none", "expected_state": "POST", "operation_key": "run26"})
    for phase in ["before_commit", "after_commit"]:
        for engine in ENGINES:
            result.append({"id": f"kill_n100000_{engine}_{phase}", "engine": engine, "n": 100000, "repeat": 0, "kill_at": phase, "expected_state": "PRE" if phase == "before_commit" else "POST", "operation_key": "run26"})
    return result


def capture(db, destination):
    from observe26 import snapshot
    destination.mkdir()
    before = snapshot(db)
    copied = {}
    for suffix in ["", "-journal", "-wal", "-shm"]:
        source = Path(str(db) + suffix)
        try:
            with source.open("rb") as inp, (destination / ("database.sqlite" + suffix)).open("xb") as out:
                shutil.copyfileobj(inp, out, 65536)
                out.flush()
                os.fsync(out.fileno())
            copied["database.sqlite" + suffix] = {"sha256": digest(destination / ("database.sqlite" + suffix)), "bytes": (destination / ("database.sqlite" + suffix)).stat().st_size}
        except FileNotFoundError:
            if suffix == "":
                raise
    after = snapshot(db)
    record = {"before": before, "after": after, "copied": copied, "time_ns": time.time_ns()}
    write_json(destination / "capture.json", record)
    return record


def run(output):
    from fixture26 import prepare
    from observe26 import environment, snapshot
    frozen = verify_freeze()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "environment.json", environment())
    fixtures = {}
    for n in [100000, 300000]:
        fixture = prepare(output / f"fixtures/n{n}", n)
        fixtures[n] = fixture
        write_json(output / f"fixtures/n{n}/fixture.json", fixture)
    write_json(output / "run_manifest.json", {"protocol_sha256": frozen["protocol_sha256"], "execution_order": frozen["execution_order"], "fixture_files": {str(p.relative_to(output)): {"sha256": digest(p), "bytes": p.stat().st_size} for p in sorted((output / "fixtures").rglob("*")) if p.is_file()}, "started_ns": time.time_ns()})
    records = []
    for spec in frozen["execution_order"]:
        trial = output / "trials" / spec["id"]
        trial.mkdir(parents=True)
        fixture = fixtures[spec["n"]]
        db = trial / "database.sqlite"
        shutil.copyfile(fixture["db"], db)
        initial = snapshot(db)
        command = [sys.executable, str(ROOT / "actor26.py"), "--db", str(db), "--csv", fixture["csv"], "--fixture-json", str(output / f"fixtures/n{spec['n']}/fixture.json"), "--engine", spec["engine"], "--trace", str(trial / "trace.jsonl"), "--kill-at", spec["kill_at"]]
        start = time.monotonic_ns()
        timed_out = False
        try:
            process = subprocess.run(command, capture_output=True, timeout=180)
            returncode, stdout, stderr = process.returncode, process.stdout, process.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            returncode, stdout, stderr = None, exc.stdout or b"", exc.stderr or b""
        elapsed = time.monotonic_ns() - start
        (trial / "stdout.txt").write_bytes(stdout)
        (trial / "stderr.txt").write_bytes(stderr)
        exit_view = snapshot(db)
        captured = capture(db, trial / "exit_capture")
        record = {"schema": "qkf.run26.record.v1", "protocol_sha256": frozen["protocol_sha256"], "spec": spec, "command": command, "fixture": fixture, "initial": initial, "returncode": returncode, "timed_out": timed_out, "wall_ns": elapsed, "exit_view": exit_view, "exit_capture": captured}
        write_json(trial / "record.json", record)
        records.append(record)
        print(json.dumps({"trial": spec["id"], "returncode": returncode}), flush=True)
    # All producers have exited; elapsed time is measured individually, not claimed equal.
    time.sleep(2)
    for record in records:
        trial = output / "trials" / record["spec"]["id"]
        record["late_capture"] = capture(trial / "database.sqlite", trial / "late_capture")
        write_json(trial / "record.json", record)
    # Cold checker runs only after capture; it never opens producers' databases.
    process = subprocess.run([sys.executable, str(ROOT / "cold26.py"), str(output)], capture_output=True, timeout=300)
    (output / "cold_stdout.txt").write_bytes(process.stdout)
    (output / "cold_stderr.txt").write_bytes(process.stderr)
    write_json(output / "completion.json", {"cold_returncode": process.returncode, "finished_ns": time.time_ns(), "freeze_verified": verify_freeze()["protocol_sha256"]})
    print(process.stdout.decode("utf-8", errors="replace"), flush=True)
    return process.returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.freeze:
        print(json.dumps(freeze(), indent=2))
    elif args.output:
        raise SystemExit(run(args.output))
    else:
        parser.error("use --freeze or --output NEW_DIRECTORY")
