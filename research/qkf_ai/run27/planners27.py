"""Public-call-only planners for the registered Run27 artifact task.

The oracle and ordinary learner use the same executor.  Oracle knowledge is
supplied by the harness; a learner derives knowledge from charged sandbox calls.
There is no language-model episode in this experiment.
"""

from dataclasses import asdict, dataclass
from typing import Any


class PlannerFailure(RuntimeError):
    """A retained public trace of a failed task/program, never a silent retry."""

    def __init__(self, message: str, *, partial_task: dict | None = None,
                 partial_program: dict | None = None) -> None:
        super().__init__(message)
        self.partial_task = partial_task
        self.partial_program = partial_program


@dataclass(frozen=True)
class Knowledge:
    fork_mode: str = "unknown"
    activation_mode: str = "unknown"

    def __post_init__(self) -> None:
        if self.fork_mode not in {"unknown", "copy", "alias"}:
            raise ValueError("unsupported fork knowledge")
        if self.activation_mode not in {"unknown", "pinned", "live"}:
            raise ValueError("unsupported activation knowledge")


def _observed_call(service: Any, trace: list, phase: str, action: str,
                   **kwargs: Any) -> dict:
    result = service.call(action, **kwargs)
    trace.append({"phase": phase, "action": action,
                  "args": kwargs, "result": result})
    return result


def _require_ok(result: dict, action: str) -> dict:
    if result.get("ok") is not True:
        raise RuntimeError(f"{action} failed: {result!r}")
    return result


def _learn(service: Any, full: bool) -> tuple[Knowledge, list[dict]]:
    """Probe an isolated artifact through the ordinary public API.

    Full learning shares the advancing write across both distinguishing tests.
    Fork-only costs 6 and full learning costs 11, including sandbox creation.
    An unexpected response raises instead of assigning unearned knowledge.
    """
    trace: list[dict] = []
    initial, advanced = "run27:probe:initial", "run27:probe:advanced"

    def call(action: str, **kwargs: Any) -> dict:
        return _observed_call(service, trace, "sandbox", action, **kwargs)

    source = _require_ok(call("create", value=initial), "create")["handle"]
    branch = _require_ok(call("fork", handle=source), "fork")["handle"]
    token = None
    if full:
        token = _require_ok(call("validate", handle=source), "validate")["token"]
    _require_ok(call("write", handle=source, value=advanced), "write")
    value = _require_ok(call("read", handle=branch), "read")["value"]
    if value == initial:
        fork_mode = "copy"
    elif value == advanced:
        fork_mode = "alias"
    else:
        raise RuntimeError("fork probe observed an unregistered outcome")
    activation_mode = "unknown"
    if full:
        published = call("activate", handle=source, token=token)
        if published.get("ok") is True and published.get("published_value") == initial:
            activation_mode = "pinned"
        elif published.get("ok") is False and published.get("error") == "token_revision_mismatch":
            activation_mode = "live"
        else:
            raise RuntimeError("activation probe observed an unregistered outcome")
    return Knowledge(fork_mode, activation_mode), trace


def learn_fork(service: Any) -> tuple[Knowledge, list[dict]]:
    return _learn(service, full=False)


def learn_full(service: Any) -> tuple[Knowledge, list[dict]]:
    return _learn(service, full=True)


def expected_portfolio_costs(task_count: int) -> dict[str, int]:
    """Costs under the registered uniform four-class prior, not true class data."""
    if type(task_count) is not int or task_count < 1:
        raise ValueError("task_count must be a positive integer")
    return {"safe": 17 * task_count,
            "fork": 6 + 15 * task_count,
            "full": 11 + 14 * task_count,
            "online": 5 + 14 * task_count}


def select_budgeted_policy(task_count: int) -> str:
    """Choose among registered arms using their prior mean costs only.

    This is a finite comparison of implemented policies, not a global optimum.
    Common rollback overhead is added by the harness and leaves this choice
    unchanged.
    """
    costs = expected_portfolio_costs(task_count)
    # Dict order intentionally favors fewer probes when registered costs tie.
    return min(costs, key=costs.get)


def execute_task(service: Any, task: dict, knowledge: Knowledge | None = None) -> dict:
    """Preserve A, validate B, advance source to C, then publish validated B.

    Only the public task and supplied/learned knowledge are read.  The executor
    cannot inspect service state or its hidden backend class.
    """
    knowledge = Knowledge() if knowledge is None else knowledge
    initial, validated, next_value = (task[key] for key in
                                     ("initial", "validated", "next_value"))
    if len({initial, validated, next_value}) != 3:
        raise ValueError("task requires three distinct values")
    trace: list[dict] = []
    handles: dict[str, str] = {}
    token = None

    def call(phase: str, action: str, **kwargs: Any) -> dict:
        result = _observed_call(service, trace, phase, action, **kwargs)
        if result.get("ok") is not True:
            partial = {"task_id": task["id"], "handles": dict(handles),
                       "token": token, "publication": result if phase == "publish" else None,
                       "knowledge": asdict(knowledge), "trace": trace,
                       "error": result}
            raise PlannerFailure(f"{action} failed: {result!r}", partial_task=partial)
        return result

    source = call("initial", "create", value=initial)["handle"]
    handles["source"] = source
    protect = "fork" if knowledge.fork_mode == "copy" else "snapshot"
    backup = call("preserve_initial", protect, handle=source)["handle"]
    handles["backup"] = backup
    call("prepare_validated", "write", handle=source, value=validated)
    token = call("validate", "validate", handle=source)["token"]
    if knowledge.activation_mode == "pinned":
        target = source
    else:
        target = call("preserve_validated", protect, handle=source)["handle"]
    handles["target"] = target
    call("advance_source", "write", handle=source, value=next_value)
    publication = call("publish", "activate", handle=target, token=token)
    return {"task_id": task["id"],
            "handles": handles,
            "token": token, "publication": publication,
            "knowledge": asdict(knowledge), "trace": trace}


def execute_program(service: Any, program: dict,
                    knowledge: Knowledge | None = None) -> dict:
    """Compose the learned primitive into public, unprobed program structures."""
    kind = program["kind"]
    components = program["components"]
    expected_components = {"publish": 1, "rollback": 1, "paired_publish": 2}
    if kind not in expected_components or len(components) != expected_components[kind]:
        raise ValueError("invalid registered program structure")
    results = []
    for component in components:
        try:
            results.append(execute_task(service, component, knowledge))
        except PlannerFailure as exc:
            exc.partial_program = {"id": program["id"], "kind": kind,
                                   "components": results + [exc.partial_task],
                                   "rollback": [], "error": str(exc)}
            raise
    rollback: list[dict] = []
    if kind == "rollback":
        backup = results[0]["handles"]["backup"]
        token = _require_ok(_observed_call(service, rollback, "rollback_validate",
                                          "validate", handle=backup), "validate")["token"]
        _require_ok(_observed_call(service, rollback, "rollback_activate", "activate",
                                  handle=backup, token=token), "activate")
    return {"id": program["id"], "kind": kind,
            "components": results, "rollback": rollback}
