"""Public programs and separately routed hidden classes for Run27."""
from __future__ import annotations

import hashlib
import json

BACKENDS = ["copy_pin", "copy_live", "alias_pin", "alias_live"]
PRIMARY_STRATEGIES = ["safe", "oracle", "ordinary_fork", "ordinary_full", "ordinary_online", "ordinary_best"]
ABLATION_STRATEGIES = ["oracle_wrong_fork", "oracle_wrong_activation"]
STRATEGIES = PRIMARY_STRATEGIES + ABLATION_STRATEGIES


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def portfolios():
    result = []
    for split in ["selection", "transfer"]:
        for count in [1, 4, 12]:
            portfolio_id = f"{split}_n{count}"
            programs = []
            for i in range(count):
                kind = "publish" if split == "selection" else ["rollback", "paired_publish"][i % 2]
                components = []
                for part in range(2 if kind == "paired_publish" else 1):
                    identifier = f"{portfolio_id}_p{i}_c{part}"
                    suffix = hashlib.sha256(identifier.encode()).hexdigest()[:16]
                    # Names/values are paired across every hidden class and arm.
                    components.append({"id": identifier, "initial": f"artifact:{suffix}:A",
                                       "validated": f"artifact:{suffix}:B", "next_value": f"artifact:{suffix}:C"})
                programs.append({"id": f"{portfolio_id}_p{i}", "kind": kind, "components": components})
            result.append({"id": portfolio_id, "split": split, "program_count": count, "programs": programs})
    return result


def specifications():
    result = []
    for portfolio in portfolios():
        for backend in BACKENDS:
            for strategy in STRATEGIES:
                fields = {"portfolio_id": portfolio["id"], "portfolio_sha256": sha(portfolio),
                          "backend": backend, "strategy": strategy}
                fields["episode_id"] = "ep_" + sha(fields)[:20]
                result.append(fields)
    return result


def manifest():
    return {"schema": "qkf.run27.manifest.v1", "portfolios": portfolios(),
            "execution_order": specifications(), "costs": {"create": 2, "read": 1, "fork": 1,
            "snapshot": 3, "write": 2, "validate": 3, "activate": 2},
            "primary_practical_gain": 0.15, "oracle_utility_gain": 0.15,
            "primary_strategies": PRIMARY_STRATEGIES, "ablation_strategies": ABLATION_STRATEGIES}
