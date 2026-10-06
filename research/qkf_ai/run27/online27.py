"""Charged online learning from the first real artifact task.

Only public calls are used. A protected first task earns both facts; subsequent
components use the same executor as oracle and sandbox learners.
"""
from dataclasses import asdict

from planners27 import Knowledge, execute_program, execute_task


def _first_task(service, task):
    trace = []

    def call(phase, action, **args):
        result = service.call(action, **args)
        trace.append({"phase": phase, "action": action,
                      "args": args, "result": result})
        return result

    def ok(phase, action, **args):
        result = call(phase, action, **args)
        if result.get("ok") is not True:
            raise RuntimeError(f"unexpected online {action} failure: {result!r}")
        return result

    initial, validated, advanced = (task[k] for k in
                                    ("initial", "validated", "next_value"))
    if len({initial, validated, advanced}) != 3:
        raise ValueError("online task needs three distinct values")
    source = ok("initial", "create", value=initial)["handle"]
    backup = ok("preserve_initial", "snapshot", handle=source)["handle"]
    branch = ok("learn_fork_branch", "fork", handle=source)["handle"]
    ok("prepare_validated", "write", handle=source, value=validated)
    observed = ok("learn_fork_read", "read", handle=branch)["value"]
    if observed == initial:
        fork_mode = "copy"
    elif observed == validated:
        fork_mode = "alias"
    else:
        raise RuntimeError("online fork observation outside registered scope")
    token = ok("validate", "validate", handle=source)["token"]
    protection = "fork" if fork_mode == "copy" else "snapshot"
    target = ok("preserve_validated", protection, handle=source)["handle"]
    ok("advance_source", "write", handle=source, value=advanced)
    publication = call("publish_probe", "activate", handle=source, token=token)
    if publication.get("ok") is True and publication.get("published_value") == validated:
        activation_mode = "pinned"
    elif publication == {"ok": False, "error": "token_revision_mismatch"}:
        activation_mode = "live"
        publication = ok("publish", "activate", handle=target, token=token)
    else:
        raise RuntimeError("online activation observation outside registered scope")
    knowledge = Knowledge(fork_mode, activation_mode)
    return {"task_id": task["id"],
            "handles": {"source": source, "backup": backup, "target": target},
            "token": token, "publication": publication,
            "knowledge": asdict(Knowledge()),
            "learned_knowledge": asdict(knowledge), "online_learning": True,
            "trace": trace}, knowledge


def execute_online_portfolio(service, programs):
    """Learn during the first component and reuse facts within one portfolio."""
    if not programs:
        raise ValueError("online portfolio requires a program")
    first = programs[0]
    expected = {"publish": 1, "rollback": 1, "paired_publish": 2}
    if first.get("kind") not in expected or len(first["components"]) != expected[first["kind"]]:
        raise ValueError("invalid registered first program")
    component, knowledge = _first_task(service, first["components"][0])
    components = [component]
    for task in first["components"][1:]:
        components.append(execute_task(service, task, knowledge))
    rollback = []
    if first["kind"] == "rollback":
        backup = component["handles"]["backup"]
        def rollback_call(phase, action, **args):
            result = service.call(action, **args)
            rollback.append({"phase": phase, "action": action,
                             "args": args, "result": result})
            if result.get("ok") is not True:
                raise RuntimeError(f"unexpected online rollback failure: {result!r}")
            return result
        token = rollback_call("rollback_validate", "validate", handle=backup)["token"]
        rollback_call("rollback_activate", "activate", handle=backup, token=token)
    executions = [{"id": first["id"], "kind": first["kind"],
                   "components": components, "rollback": rollback}]
    executions.extend(execute_program(service, program, knowledge) for program in programs[1:])
    return executions, knowledge
