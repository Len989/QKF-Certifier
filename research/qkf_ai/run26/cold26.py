"""Separate cold orchestrator: complete registered census and independent pair checks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from audit26 import audit_pair
from observe26 import snapshot
from run26 import verify_freeze, write_json


def file_sha(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(65536):
            result.update(block)
    return result.hexdigest()


def view(snapshot_value):
    if set(snapshot_value["files"]) != {"database", "-journal", "-wal", "-shm"}:
        raise ValueError("file observation census differs")
    result = {}
    for key, item in snapshot_value["files"].items():
        if item.get("exists") is False and item.get("error", {}).get("type") == "FileNotFoundError":
            result[key] = None
        elif item.get("exists") is True and item.get("stable_during_read") is True and not item.get("error"):
            result[key] = {"sha256": item["sha256"], "bytes": item["bytes_read"]}
        else:
            raise ValueError(f"unstable/failed file observation {key}: {item}")
    if "error" in snapshot_value.get("directory", {}):
        raise ValueError("directory observation failed")
    return result


def validate_trace(observations, spec):
    """Reject missing evidence, reordered calls, and unestablished actual kill points."""
    if not observations or [o["seq"] for o in observations] != list(range(1, len(observations) + 1)) or len({o["pid"] for o in observations}) != 1:
        raise ValueError("trace sequence/PID incomplete")
    if any(a["observation_finished_monotonic_ns"] > b["monotonic_ns"] for a, b in zip(observations, observations[1:])):
        raise ValueError("trace monotonic ordering invalid")
    events = [o["event"] for o in observations]
    if events[0] != "actor_started" or events.count("connection_opened") != 1 or events.count("before_commit") != 1:
        raise ValueError("actor start/connection/commit census differs")
    if observations[0]["engine"] != spec["engine"] or observations[0]["kill_at"] != spec["kill_at"]:
        raise ValueError("actor treatment binding differs")
    for observation in observations:
        if observation["event"] != "kill_requested":
            view(observation["snapshot"])
        if observation["event"] == "before_commit" and observation["in_transaction"] is not True:
            raise ValueError("commit was not in a transaction")
        if observation["event"] == "after_commit" and (observation["call_returned"] is not True or observation["in_transaction"] is not False):
            raise ValueError("commit successful return not established")
        if observation["event"] == "after_close" and observation["call_returned"] is not True:
            raise ValueError("close successful return not established")
    if spec["kill_at"] == "none":
        required = ["before_commit", "after_commit", "before_close", "after_close", "actor_returned"]
        if any(events.count(event) != 1 for event in required) or events[-1] != "actor_returned":
            raise ValueError("normal completion missing commit/close/return")
        positions = [events.index(event) for event in required]
        if positions != sorted(positions) or "kill_requested" in events or "actor_exception" in events:
            raise ValueError("normal call order differs")
    else:
        if events[-1] != "kill_requested" or observations[-1].get("at") != spec["kill_at"] or events.count("kill_requested") != 1 or events[-2] != spec["kill_at"]:
            raise ValueError("kill point not established")
        if any(event in events for event in ["before_close", "after_close", "actor_returned", "actor_exception"]):
            raise ValueError("killed actor unexpectedly closed/returned")
        if events.count("after_commit") != (1 if spec["kill_at"] == "after_commit" else 0):
            raise ValueError("wrong actual commit boundary for kill")
    return events


def main(output):
    frozen = verify_freeze()
    manifest = json.loads((output / "run_manifest.json").read_text())
    if manifest["protocol_sha256"] != frozen["protocol_sha256"] or manifest["execution_order"] != frozen["execution_order"]:
        raise ValueError("run manifest differs from preregistration")
    for path, item in manifest["fixture_files"].items():
        source = output / path
        if source.stat().st_size != item["bytes"] or file_sha(source) != item["sha256"]:
            raise ValueError(f"fixture hash mismatch: {path}")
    registered = {s["id"] for s in frozen["execution_order"]}
    actual = {p.name for p in (output / "trials").iterdir()}
    if registered != actual:
        raise ValueError("trial census differs from preregistration")
    results = []
    for spec in frozen["execution_order"]:
        trial = output / "trials" / spec["id"]
        errors = []
        result = {"spec": spec, "captures": {}, "errors": errors}
        try:
            record = json.loads((trial / "record.json").read_text())
            if record["spec"] != spec or record["protocol_sha256"] != frozen["protocol_sha256"]:
                raise ValueError("record spec/protocol binding differs")
            expected_returncode = 0 if spec["kill_at"] == "none" else -9
            if record["timed_out"] or record["returncode"] != expected_returncode:
                errors.append(f"unexpected actor exit: {record['returncode']}")
            observations = [json.loads(line) for line in (trial / "trace.jsonl").read_text().splitlines()]
            events = validate_trace(observations, spec)
            fixture = json.loads((output / f"fixtures/n{spec['n']}/fixture.json").read_text())
            if record["fixture"] != fixture or view(record["initial"])["database"]["sha256"] != fixture["initial_db_sha"]:
                errors.append("initial physical fixture differs")
            # Original absolute paths are evidence, not authority after transfer.
            audit_fixture = dict(fixture, csv=str(output / f"fixtures/n{spec['n']}/input.csv"),
                                 db=str(output / f"fixtures/n{spec['n']}/initial.sqlite"))
            exit_view = view(record["exit_view"])
            if exit_view["-wal"] is not None or exit_view["-shm"] is not None:
                errors.append("unexpected WAL/SHM in DELETE protocol")
            if spec["expected_state"] == "POST" and exit_view["-journal"] is not None:
                errors.append("journal remains visible after commit/exit")
            for observation in observations:
                if "snapshot" in observation:
                    current = view(observation["snapshot"])
                    if observation["event"] in ("after_commit", "before_close", "after_close", "actor_returned") and current != exit_view:
                        errors.append("post-commit producer view differs from exit at " + observation["event"])
                    if observation["event"] == "before_commit":
                        settings = observation["settings"]
                        if settings["journal_mode"] != "delete" or settings["synchronous"] != 2 or settings["temp_store"] != 1:
                            errors.append("transaction journal/sync/temp policy differs")
                        if spec["kill_at"] == "before_commit" and current != exit_view:
                            errors.append("precommit kill files differ from parent exit")
            if spec["engine"] == "minimal_pressure":
                if not any(o["event"] == "pressure_allocated" and o["allocated_bytes"] == 256 * 1024 * 1024 for o in observations):
                    errors.append("memory treatment missing")
            before_original = view(snapshot(trial / "database.sqlite"))
            if before_original != exit_view:
                errors.append("producer files changed after late capture before cold audit")
            for point in ["exit", "late"]:
                capture = record[point + "_capture"]
                before, after = view(capture["before"]), view(capture["after"])
                if before != after or before != exit_view:
                    errors.append(point + " capture source changed/differs from actor exit")
                pairdir = trial / (point + "_capture")
                if json.loads((pairdir / "capture.json").read_text()) != capture:
                    errors.append(point + " capture metadata differs from record")
                retained = {p.name for p in pairdir.iterdir() if p.is_file() and p.name != "capture.json"}
                if retained != set(capture["copied"]):
                    errors.append(point + " artifact file census differs")
                expected_copied = {"database.sqlite" + ("" if key == "database" else key): info for key, info in before.items() if info is not None}
                if expected_copied != capture["copied"]:
                    errors.append(point + " copied hash differs from source observation")
                for name, info in capture["copied"].items():
                    path = pairdir / name
                    if path.stat().st_size != info["bytes"] or file_sha(path) != info["sha256"]:
                        errors.append(point + " retained file hash differs")
                audited = audit_pair(pairdir, spec, audit_fixture)
                result["captures"][point] = audited
                if not audited["pass"] or audited["state"] != spec["expected_state"]:
                    errors.append(point + " cold state differs: " + audited["state"])
            if before_original != view(snapshot(trial / "database.sqlite")):
                errors.append("cold audit modified producer originals")
            result["events"] = events
            result["late_delay_ns"] = record["late_capture"]["time_ns"] - record["exit_capture"]["time_ns"]
            result["journal_after_commit"] = any(o["event"] == "after_commit" and view(o["snapshot"])["-journal"] is not None for o in observations)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        result["pass"] = not errors
        results.append(result)
    passed = sum(r["pass"] for r in results)
    states = {}
    for result in results:
        for captured in result["captures"].values():
            states[captured["state"]] = states.get(captured["state"], 0) + 1
    summary = {"schema": "qkf.run26.summary.v1", "protocol_sha256": frozen["protocol_sha256"], "registered_trials": 30, "observed_trials": len(results), "passed_trials": passed, "failed_trials": len(results) - passed, "consistency_gate": "PASS" if passed == 30 else "FAIL", "release_status": "BLOCKED_PENDING_RUN25_CAUSE", "normal_trials": sum(r["spec"]["kill_at"] == "none" for r in results), "sigkill_trials": sum(r["spec"]["kill_at"] != "none" for r in results), "cold_pairs": sum(len(r["captures"]) for r in results), "cold_states": states, "results": results}
    write_json(output / "summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False, indent=2))
    return 0 if passed == 30 else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve()))
