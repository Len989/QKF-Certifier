"""Complete census, retained-byte binding and separate goal/cost analysis."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from check27 import audit_episode
from run27 import file_sha, verify_freeze, write


def gain(before, after):
    return (before - after) / before


def comparisons_and_strata(results, planned, cost_key):
    paired = {}
    for result in results:
        key = (result["spec"]["portfolio_id"], result["spec"]["backend"])
        paired.setdefault(key, {})[result["spec"]["strategy"]] = result
    comparisons = []
    for (portfolio_id, backend), arms in paired.items():
        costs = {s: arms[s][cost_key] for s in planned["primary_strategies"]}
        comparisons.append({"portfolio_id": portfolio_id, "backend": backend,
            "costs": costs, "oracle_vs_safe_gain": gain(costs["safe"], costs["oracle"]),
            "oracle_vs_ordinary_best_gain": gain(costs["ordinary_best"], costs["oracle"]),
            "ordinary_best_vs_safe_gain": gain(costs["safe"], costs["ordinary_best"])})
    strata = []
    for portfolio in planned["portfolios"]:
        rows = [r for r in comparisons if r["portfolio_id"] == portfolio["id"]]
        totals = {s: sum(r["costs"][s] for r in rows) for s in planned["primary_strategies"]}
        strata.append({"portfolio_id": portfolio["id"], "split": portfolio["split"], "program_count": portfolio["program_count"],
            "component_count": sum(len(p["components"]) for p in portfolio["programs"]),
            "costs_sum_four_classes": totals,
            "oracle_vs_safe_gain": gain(totals["safe"], totals["oracle"]),
            "oracle_vs_ordinary_best_gain": gain(totals["ordinary_best"], totals["oracle"]),
            "ordinary_best_vs_safe_gain": gain(totals["safe"], totals["ordinary_best"])})
    return comparisons, strata


def audit(output):
    frozen = verify_freeze()
    planned = frozen["manifest"]
    actual_manifest = json.loads((output / "manifest.json").read_text())
    if actual_manifest != planned:
        raise ValueError("public programs/specifications differ from freeze")
    retained = json.loads((output / "artifact_manifest.json").read_text())
    if retained["protocol_sha256"] != frozen["protocol_sha256"]:
        raise ValueError("artifact protocol differs")
    specs = planned["execution_order"]
    expected_files = {"episodes/" + s["episode_id"] + ".json" for s in specs}
    observed_files = {str(p.relative_to(output)) for p in (output / "episodes").iterdir()}
    if expected_files != observed_files or expected_files != set(retained["files"]):
        raise ValueError("episode census differs from registration")
    portfolios = {p["id"]: p for p in planned["portfolios"]}
    results = []
    for spec in specs:
        relative = "episodes/" + spec["episode_id"] + ".json"
        path = output / relative
        item = retained["files"][relative]
        if file_sha(path) != item["sha256"] or path.stat().st_size != item["bytes"]:
            raise ValueError("retained bytes changed: " + relative)
        record = json.loads(path.read_text())
        if any(record.get(key) != value for key, value in spec.items()):
            raise ValueError("episode spec binding differs: " + relative)
        checked = audit_episode(record, portfolios[spec["portfolio_id"]], spec["backend"], spec["strategy"], frozen["protocol_sha256"])
        events = record["services"]["task"]["log"] + (record["services"]["probe"]["log"] if record["services"]["probe"] else [])
        trusted_cost = checked["task_cost"] + checked["probe_cost"] if checked["integrity_pass"] else None
        write_heavy = {**planned["costs"], "create": 5, "write": 10}
        results.append({"spec": spec, "audit": checked, "cost": trusted_cost,
                        "equal_call_cost": len(events) if checked["integrity_pass"] else None,
                        "write_heavy_cost": sum(write_heavy.get(e["action"], 1) for e in events) if checked["integrity_pass"] else None,
                        "task_calls": len(record["services"]["task"]["log"]),
                        "probe_calls": len(record["services"]["probe"]["log"]) if record["services"]["probe"] else 0})
    primary = [r for r in results if r["spec"]["strategy"] in planned["primary_strategies"]]
    ablations = [r for r in results if r["spec"]["strategy"] in planned["ablation_strategies"]]
    integrity_pass = all(r["audit"]["integrity_pass"] for r in results)
    correctness_pass = all(r["audit"]["goal_pass"] for r in primary)
    expected_ablations = []
    for r in ablations:
        backend, strategy = r["spec"]["backend"], r["spec"]["strategy"]
        want = not (backend.startswith("alias") if strategy == "oracle_wrong_fork" else backend.endswith("live"))
        expected_ablations.append(r["audit"]["goal_pass"] == want)
    ablation_pass = all(expected_ablations)
    comparisons = []
    strata = []
    sensitivity = []
    if integrity_pass:
        comparisons, strata = comparisons_and_strata(results, planned, "cost")
        for name, key, prices in [("equal_call", "equal_call_cost", {a: 1 for a in planned["costs"]}),
                                  ("write_heavy", "write_heavy_cost", {**planned["costs"], "create": 5, "write": 10})]:
            _, alternate = comparisons_and_strata(results, planned, key)
            sensitivity.append({"price_model": name, "prices": prices, "fixed_original_plans": True,
                                "policy_reoptimized": False, "strata": alternate})
    # Each public stratum must meet the preregistered threshold; do not hide
    # failed small portfolios in a large pooled total.
    transfer = [s for s in strata if s["split"] == "transfer"]
    consistent = integrity_pass and correctness_pass and ablation_pass
    utility = consistent and bool(transfer) and all(s["oracle_vs_safe_gain"] >= planned["oracle_utility_gain"] for s in transfer)
    practical = consistent and bool(transfer) and all(s["oracle_vs_ordinary_best_gain"] >= planned["primary_practical_gain"] for s in transfer)
    summary = {"schema": "qkf.run27.summary.v1", "protocol_sha256": frozen["protocol_sha256"],
        "registered_episodes": len(specs), "audited_episodes": len(results),
        "integrity_passed": sum(r["audit"]["integrity_pass"] for r in results),
        "primary_episodes": len(primary), "primary_goals_passed": sum(r["audit"]["goal_pass"] for r in primary),
        "ablation_episodes": len(ablations), "ablation_goals_failed": sum(not r["audit"]["goal_pass"] for r in ablations),
        "consistency_gate": "PASS" if integrity_pass and correctness_pass and ablation_pass else "FAIL",
        "interface_causal_use_gate": "PASS" if correctness_pass and ablation_pass and integrity_pass else "FAIL",
        "oracle_utility_gate": "PASS" if utility else "FAIL",
        "beyond_strong_ordinary_gate": "PASS" if practical else "FAIL",
        "csv_release_status": "BLOCKED_BY_UNRESOLVED_RUN25_RUN26",
        "llm_episodes": 0, "strata": strata, "comparisons": comparisons,
        "price_sensitivity": sensitivity, "results": results}
    write(output / "summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in ["results", "comparisons"]}, ensure_ascii=False, indent=2))
    return 0 if summary["consistency_gate"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    raise SystemExit(audit(args.output.resolve()))
