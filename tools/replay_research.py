#!/usr/bin/env python3
"""Replay saved research proofs without running producers or SMT.

These profiles use Python 3.12 and Linux/POSIX. Their contracts and schemas
are separate from those of the installable coordinatewise CLI.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command, cwd, log, timeout=240):
    process = subprocess.run(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    log.write_text(process.stdout, encoding="utf-8")
    if process.returncode:
        raise RuntimeError(f"Command failed; inspect {log}")


def verify_origin(root):
    origin = json.loads((root / "CAPSULE_ORIGIN.json").read_text())
    for relative, expected in origin["files_preserved"].items():
        path = root / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Frozen source/evidence differs: {path}")


def graal(output):
    root = ROOT / "research" / "graal"
    verify_origin(root)
    run(
        [sys.executable, str(root / "replay_saved.py"), "--output", str(output / "graal")],
        root,
        output / "graal.log",
    )
    result = json.loads((output / "graal" / "results.json").read_text())
    if result["status"] != "passed" or result["fresh_proof_processes"] != 7:
        raise ValueError("Incomplete Graal replay")
    return {
        "status": "passed",
        "fresh_proof_processes": 7,
        "upper": "exact masked maximum and empty-case distinction",
        "lower": "conditional carrier preservation",
        "complete_graal_results": "control 1/5; joint 2/5",
    }


def knownbits(output, selected):
    root = ROOT / "research" / "knownbits"
    verify_origin(root)
    run([sys.executable, str(root / "restore_data.py")], root, output / "restore.log")
    saved = root / "results_v2" / "observed"
    names = sorted(p.parent.name for p in (root / "fixtures" / "corpus").glob("*/solution.mlir"))
    if len(names) != 39:
        raise ValueError("Expected the complete 39-program source population")
    if selected:
        if selected not in names:
            raise ValueError("Unknown case")
        names = [selected]
    records = []
    logs = output / "knownbits"
    logs.mkdir()
    for name in names:
        with tempfile.TemporaryDirectory(prefix="qkf_replay_", dir=output) as temp:
            work = Path(temp)
            for directory in ["producer", "prepared", "certificates"]:
                source = saved / directory / f"{name}.json"
                if source.exists():
                    destination = work / directory / source.name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
            run(
                [
                    sys.executable,
                    str(root / "result_v2_run.py"),
                    "--mode",
                    "observed",
                    "--case",
                    name,
                    "--worker",
                    "replay",
                    "--output",
                    str(work),
                ],
                root,
                logs / f"{name}.log",
                timeout=75,
            )
            record = json.loads((work / "replay" / f"{name}.json").read_text())
            accepted = {
                "proved_original_whole_all_positive_widths",
                "all_preparations_and_available_proofs_replayed",
            }
            if record.get("status") not in accepted or record.get("search_modules_loaded"):
                raise ValueError(f"Research replay failed: {name}: {record.get('status')}")
            (logs / f"{name}.json").write_text(json.dumps(record, indent=2) + "\n")
            records.append(record)
            print(f"{name}: {record['status']}", flush=True)
    whole = sum(r["status"] == "proved_original_whole_all_positive_widths" for r in records)
    components = sum(r["components"] for r in records)
    proved = sum(r["component_target_proofs"] for r in records)
    if not selected and (len(records), whole, components, proved) != (39, 11, 411, 104):
        raise ValueError("Coverage differs from the retained result-observation stage")
    return {
        "status": "passed",
        "programs_checked": len(records),
        "complete_programs_proved": whole,
        "source_components_checked": components,
        "component_target_proofs": proved,
        "search_or_smt_loaded": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=["knownbits", "graal", "all"], default="all")
    parser.add_argument("--case", help="One KnownBits case, for example KnownBits_Add")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not __debug__:
        raise SystemExit("Run without -O/-OO: research assertions are required")
    if sys.platform == "win32" or sys.version_info < (3, 12):
        raise SystemExit("Use Python 3.12+ on Linux/POSIX for this research runner")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {"status": "passed", "suites": {}}
    if args.suite in {"knownbits", "all"}:
        result["suites"]["knownbits"] = knownbits(output, args.case)
    if args.suite in {"graal", "all"}:
        result["suites"]["graal"] = graal(output)
    (output / "RESULTS.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
