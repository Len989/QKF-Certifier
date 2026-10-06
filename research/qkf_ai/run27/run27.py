"""Frozen paired experiment; execution and independent cold replay stay distinct."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

from scenarios27 import canonical, manifest, sha

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]


def write(path, data):
    Path(path).write_text(canonical(data) + "\n", encoding="utf-8")


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sources():
    paths = sorted(ROOT.glob("*.py")) + [ROOT / "PROTOCOL_RU.md", REPO / ".github/workflows/qkf-ai-run27.yml"]
    return {str(path.relative_to(REPO)): file_sha(path) for path in paths}


def freeze():
    body = {"schema": "qkf.run27.freeze.v1", "source_sha256": sources(), "manifest": manifest()}
    body["protocol_sha256"] = sha(body)
    write(ROOT / "PROTOCOL_FREEZE.json", body)
    return body


def verify_freeze():
    frozen = json.loads((ROOT / "PROTOCOL_FREEZE.json").read_text())
    body = {k: v for k, v in frozen.items() if k != "protocol_sha256"}
    if sha(body) != frozen["protocol_sha256"] or sources() != frozen["source_sha256"] or manifest() != frozen["manifest"]:
        raise ValueError("source/protocol/manifest freeze mismatch")
    return frozen


class PublicCalls:
    """Only call is exposed; this Python wrapper is not an adversarial sandbox."""
    def __init__(self, callback):
        self._callback = callback

    def call(self, action, **args):
        return self._callback(action, **args)


def episode(spec, portfolio, protocol):
    from planners27 import Knowledge, execute_program, learn_fork, learn_full, select_budgeted_policy, expected_portfolio_costs
    from service27 import ArtifactService
    from online27 import execute_online_portfolio
    units = sum(len(p["components"]) for p in portfolio["programs"])
    overhead = 5 * sum(p["kind"] == "rollback" for p in portfolio["programs"])
    predicted = {key: value + overhead for key, value in expected_portfolio_costs(units).items()}
    strategy = spec["strategy"]
    chosen = {"ordinary_fork": "fork", "ordinary_full": "full", "ordinary_online": "online", "safe": "safe"}.get(strategy)
    if strategy == "ordinary_best":
        chosen = select_budgeted_policy(units)
    knowledge = Knowledge()
    source = "safe"
    probe = None
    probe_trace = []
    task = ArtifactService(spec["backend"], seed=portfolio["id"] + ":task")
    executions = []
    error = None
    started = time.monotonic_ns()
    if chosen in ["fork", "full"]:
        probe = ArtifactService(spec["backend"], seed=portfolio["id"] + ":probe")
        learner = learn_fork if chosen == "fork" else learn_full
        source = "charged_probe_" + chosen
        try:
            knowledge, probe_trace = learner(PublicCalls(probe.call))
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc), "program_id": None, "phase": "acquisition"}
    elif strategy.startswith("oracle"):
        fork_mode, activation = spec["backend"].split("_")
        activation = "pinned" if activation == "pin" else "live"
        if strategy == "oracle_wrong_fork":
            fork_mode = "alias" if fork_mode == "copy" else "copy"
        elif strategy == "oracle_wrong_activation":
            activation = "live" if activation == "pinned" else "pinned"
        knowledge = Knowledge(fork_mode, activation)
        source = {"oracle": "oracle", "oracle_wrong_fork": "oracle_ablation_fork", "oracle_wrong_activation": "oracle_ablation_activation"}[strategy]
        chosen = strategy
    if chosen == "online":
        source = "charged_task_observations"
        try:
            executions, knowledge = execute_online_portfolio(PublicCalls(task.call), portfolio["programs"])
        except Exception as exc:
            partial = getattr(exc, "partial_program", None)
            if partial is not None:
                executions.append(partial)
            error = {"type": type(exc).__name__, "message": str(exc), "program_id": None, "phase": "online"}
    for program in ([] if chosen == "online" or error else portfolio["programs"]):
        try:
            executions.append(execute_program(PublicCalls(task.call), program, knowledge))
        except Exception as exc:
            partial = getattr(exc, "partial_program", None)
            if partial is not None:
                executions.append(partial)
            error = {"type": type(exc).__name__, "message": str(exc), "program_id": program["id"]}
            break
    def service_record(service, seed):
        return {"seed": seed, "log": service.export_log(), "final_state": service.export_state(), "total_cost": service.total_cost}
    record = {"schema": "qkf.run27.record.v1", **spec, "protocol_sha": protocol,
              "knowledge": {**asdict(knowledge), "source": source},
              "interface_scope": {"model": "qkf.artifact.logical.v1", "portfolio_id": portfolio["id"]},
              "policy": {"chosen": chosen, "predicted_costs": predicted},
              "services": {"probe": service_record(probe, portfolio["id"] + ":probe") if probe else None,
                           "task": service_record(task, portfolio["id"] + ":task")},
              "probe_trace": probe_trace, "executions": executions, "execution_error": error,
              "total_cost": task.total_cost + (probe.total_cost if probe else 0),
              "execution_wall_ns": time.monotonic_ns() - started}
    return record


def run(output):
    frozen = verify_freeze()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "episodes").mkdir()
    write(output / "environment.json", {"python": sys.version, "platform": platform.platform(), "protocol_sha256": frozen["protocol_sha256"]})
    write(output / "manifest.json", frozen["manifest"])
    public = {p["id"]: p for p in frozen["manifest"]["portfolios"]}
    files = {}
    for spec in frozen["manifest"]["execution_order"]:
        path = output / "episodes" / (spec["episode_id"] + ".json")
        write(path, episode(spec, public[spec["portfolio_id"]], frozen["protocol_sha256"]))
        files[str(path.relative_to(output))] = {"sha256": file_sha(path), "bytes": path.stat().st_size}
    write(output / "artifact_manifest.json", {"protocol_sha256": frozen["protocol_sha256"], "files": files})
    # No verifier modules are imported during execution. Separate cold process.
    process = subprocess.run([sys.executable, str(ROOT / "audit27.py"), str(output)], capture_output=True, timeout=90)
    (output / "cold_stdout.txt").write_bytes(process.stdout)
    (output / "cold_stderr.txt").write_bytes(process.stderr)
    write(output / "completion.json", {"cold_returncode": process.returncode, "freeze_verified": verify_freeze()["protocol_sha256"]})
    print(process.stdout.decode(errors="replace"), flush=True)
    if process.stderr:
        print(process.stderr.decode(errors="replace"), file=sys.stderr)
    return process.returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.freeze:
        print(freeze()["protocol_sha256"])
    elif args.output:
        raise SystemExit(run(args.output))
    else:
        parser.error("use --freeze or --output NEW_DIRECTORY")
