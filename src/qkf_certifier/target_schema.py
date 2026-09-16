"""Unified target request schema helpers.

Version 1 keeps routing separate from existing verification engines.
"""

from dataclasses import dataclass

SUPPORTED_KINDS = {"word_result", "boolean_predicate", "successor", "masked_bound"}


@dataclass(frozen=True)
class TargetRequest:
    kind: str
    name: str
    parameters: dict


def parse_target(data: dict) -> TargetRequest:
    if data.get("schema") != "qkf-target-v1":
        raise ValueError("unsupported target schema")
    goal = data.get("goal")
    if not isinstance(goal, dict):
        raise ValueError("missing goal")
    kind = goal.get("kind")
    if kind not in SUPPORTED_KINDS:
        raise ValueError("unsupported target kind")
    name = goal.get("name", "")
    params = goal.get("parameters", {})
    if not isinstance(name, str) or not isinstance(params, dict):
        raise ValueError("invalid target")
    return TargetRequest(kind, name, params)
