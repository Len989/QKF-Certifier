"""Independent Run27 replay and task-goal checker.

Imports only Python's standard library.  It does not trust planner goal flags,
producer costs, or producer state hashes.  Backend semantics are supplied by
registered expected metadata, not discovered from an episode's declarations.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


class AuditError(ValueError):
    pass


_CHARGES = {"create": 2, "read": 1, "fork": 1, "snapshot": 3,
            "write": 2, "validate": 3, "activate": 2}
_PARAMS = {"create": {"value"}, "read": {"handle"}, "fork": {"handle"},
           "snapshot": {"handle"}, "write": {"handle", "value"},
           "validate": {"handle"}, "activate": {"handle", "token"}}
_CLASSES = {"copy_pin", "copy_live", "alias_pin", "alias_live"}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _equal(left: Any, right: Any, label: str) -> None:
    # JSON canonical comparison preserves the distinction true versus 1.
    if _canonical(left) != _canonical(right):
        raise AuditError(f"{label}: mismatch")


def _require(condition: bool, label: str) -> None:
    if not condition:
        raise AuditError(label)


def _empty() -> dict:
    return {"cells": {}, "handles": {}, "tokens": {}, "live": None,
            "validated_revisions": [], "next_revision": 1,
            "next_handle": 1, "next_cell": 1, "next_token": 1}


def _id(seed: str, namespace: str, ordinal: int) -> str:
    return namespace + "_" + _hash([seed, namespace, ordinal])[:24]


def _transition(before: dict, action: str, args: dict,
                backend: str, seed: str) -> tuple[dict, dict]:
    """Apply the public mathematical contract to a detached state."""
    state = copy.deepcopy(before)

    def error(reason: str) -> tuple[dict, dict]:
        return copy.deepcopy(before), {"ok": False, "error": reason}

    if action not in _PARAMS:
        return error("unknown_operation")
    if set(args) != _PARAMS[action] or any(type(v) is not str for v in args.values()):
        return error("invalid_arguments")

    def allocate(namespace: str, counter: str) -> str:
        identifier = _id(seed, namespace, state[counter])
        state[counter] += 1
        return identifier

    if action == "create":
        revision = state["next_revision"]
        state["next_revision"] += 1
        cell = allocate("c", "next_cell")
        handle = allocate("h", "next_handle")
        state["cells"][cell] = {"revision": revision, "value": args["value"]}
        state["handles"][handle] = cell
        return state, {"ok": True, "handle": handle, "revision": revision,
                       "value": args["value"]}

    handle = args["handle"]
    if handle not in state["handles"]:
        return error("unknown_handle")
    source_cell = state["handles"][handle]
    current = state["cells"][source_cell]
    if action == "read":
        return state, {"ok": True, **current}
    if action in {"fork", "snapshot"}:
        if action == "snapshot" or backend.startswith("copy_"):
            target_cell = allocate("c", "next_cell")
            state["cells"][target_cell] = copy.deepcopy(current)
        else:
            target_cell = source_cell
        target = allocate("h", "next_handle")
        state["handles"][target] = target_cell
        return state, {"ok": True, "handle": target, **current}
    if action == "write":
        revision = state["next_revision"]
        state["next_revision"] += 1
        state["cells"][source_cell] = {"revision": revision, "value": args["value"]}
        return state, {"ok": True, "revision": revision}
    if action == "validate":
        token = allocate("t", "next_token")
        state["tokens"][token] = {"created_handle": handle, **current}
        state["validated_revisions"] = sorted(set(state["validated_revisions"])
                                                | {current["revision"]})
        return state, {"ok": True, "token": token,
                       "revision": current["revision"]}
    token_id = args["token"]
    if token_id not in state["tokens"]:
        return error("unknown_token")
    validated = state["tokens"][token_id]
    if backend.endswith("_live") and current["revision"] != validated["revision"]:
        return error("token_revision_mismatch")
    published = current if backend.endswith("_live") else validated
    state["live"] = {"handle": handle, "token": token_id,
                     "revision": published["revision"], "value": published["value"]}
    return state, {"ok": True, "published_revision": published["revision"],
                   "published_value": published["value"]}


def replay_service(record: dict, expected_backend: str) -> dict:
    """Replay a fresh service record {seed,log,final_state,total_cost}.

    Returned snapshots are checker-derived, useful for independent phase goals.
    A supplied initial_state, if any, must be the registered empty state.
    """
    _require(expected_backend in _CLASSES, "unregistered expected backend")
    _require(type(record) is dict, "service record must be an object")
    seed, log = record.get("seed"), record.get("log")
    _require(type(seed) is str and type(log) is list, "service seed/log malformed")
    state = _empty()
    if "initial_state" in record:
        _equal(record["initial_state"], state, "initial state")
    states, events, total = [copy.deepcopy(state)], [], 0
    expected_keys = {"index", "action", "args", "result", "cost", "total_cost",
                     "before_sha256", "after_sha256"}
    for position, event in enumerate(log, 1):
        _require(type(event) is dict and set(event) == expected_keys,
                 f"event {position}: fields")
        _require(type(event["index"]) is int and event["index"] == position,
                 f"event {position}: index")
        action, args = event["action"], event["args"]
        _require(type(action) is str and type(args) is dict,
                 f"event {position}: request types")
        _equal(event["before_sha256"], _hash(state), f"event {position}: before hash")
        next_state, result = _transition(state, action, args, expected_backend, seed)
        _equal(event["result"], result, f"event {position}: result")
        charge = _CHARGES.get(action, 1)
        _require(type(event["cost"]) is int and event["cost"] == charge,
                 f"event {position}: cost")
        total += charge
        _require(type(event["total_cost"]) is int and event["total_cost"] == total,
                 f"event {position}: cumulative cost")
        _equal(event["after_sha256"], _hash(next_state), f"event {position}: after hash")
        state = next_state
        states.append(copy.deepcopy(state))
        events.append({"index": position, "action": action,
                       "args": copy.deepcopy(args), "result": result, "cost": charge})
    _equal(record.get("final_state"), state, "whole terminal state")
    _require(type(record.get("total_cost")) is int and record["total_cost"] == total,
             "service total cost")
    return {"state": state, "states": states, "events": events,
            "cost": total, "calls": len(events)}


def _true_knowledge(backend: str) -> dict:
    fork, activation = backend.split("_")
    return {"fork_mode": fork,
            "activation_mode": "pinned" if activation == "pin" else "live"}


def _probe_knowledge(replay: dict, mode: str) -> dict:
    events = replay["events"]
    sequence = ["create", "fork", "write", "read"] if mode == "fork" else [
        "create", "fork", "validate", "write", "read", "activate"]
    _equal([e["action"] for e in events], sequence, "charged probe sequence")
    first, branch = events[:2]
    _require(first["result"].get("ok") is True and branch["result"].get("ok") is True,
             "probe creation failed")
    source = first["result"]["handle"]
    fork_handle = branch["result"]["handle"]
    _equal(first["args"], {"value": "run27:probe:initial"}, "probe initial value")
    _equal(branch["args"], {"handle": source}, "probe branch input")
    write, read = (events[2], events[3]) if mode == "fork" else (events[3], events[4])
    _equal(write["args"], {"handle": source, "value": "run27:probe:advanced"},
           "probe advancement")
    _equal(read["args"], {"handle": fork_handle}, "probe observation handle")
    observed = read["result"].get("value")
    _require(observed in {"run27:probe:initial", "run27:probe:advanced"},
             "probe unexpected observed value")
    facts = {"fork_mode": "copy" if observed == "run27:probe:initial" else "alias",
             "activation_mode": "unknown"}
    if mode == "full":
        validation, activation = events[2], events[5]
        _equal(validation["args"], {"handle": source}, "probe validation handle")
        _equal(activation["args"], {"handle": source,
                                  "token": validation["result"]["token"]},
               "probe activation input")
        result = activation["result"]
        if result.get("ok") is True:
            _require(result["published_value"] == "run27:probe:initial",
                     "probe published value")
            facts["activation_mode"] = "pinned"
        else:
            _equal(result, {"ok": False, "error": "token_revision_mismatch"},
                   "probe error")
            facts["activation_mode"] = "live"
    _require(replay["cost"] == (6 if mode == "fork" else 11), "probe total charge")
    return facts


def _program_goals(program: dict, replay: dict) -> dict:
    """Derive source, immutable revisions and phase barriers from public values."""
    errors, components = [], []
    events, states, terminal = replay["events"], replay["states"], replay["state"]
    kind, tasks = program.get("kind"), program.get("components")
    if kind not in {"publish", "rollback", "paired_publish"} or type(tasks) is not list:
        return {"id": program.get("id"), "pass": False,
                "errors": ["unregistered program structure"], "components": []}
    if len(tasks) != (2 if kind == "paired_publish" else 1):
        return {"id": program.get("id"), "pass": False,
                "errors": ["incorrect component count"], "components": []}

    def need(condition: bool, label: str) -> None:
        if not condition:
            errors.append(label)

    for task in tasks:
        task_id = task.get("id")
        initial, validated, advanced = (task.get(k) for k in
                                        ("initial", "validated", "next_value"))
        if any(type(v) is not str for v in (initial, validated, advanced)) or len(
                {initial, validated, advanced}) != 3:
            errors.append(f"{task_id}: malformed public task")
            continue
        creates = [e for e in events if e["action"] == "create"
                   and e["args"] == {"value": initial} and e["result"].get("ok") is True]
        if len(creates) != 1:
            errors.append(f"{task_id}: exactly one source creation required")
            continue
        created = creates[0]
        source, original_revision = created["result"]["handle"], created["result"]["revision"]
        writes_b = [e for e in events if e["action"] == "write"
                    and e["args"] == {"handle": source, "value": validated}
                    and e["result"].get("ok") is True]
        writes_c = [e for e in events if e["action"] == "write"
                    and e["args"] == {"handle": source, "value": advanced}
                    and e["result"].get("ok") is True]
        if len(writes_b) != 1 or len(writes_c) != 1:
            errors.append(f"{task_id}: one B and one C write required")
            continue
        b_write, c_write = writes_b[0], writes_c[0]
        b_revision, c_revision = b_write["result"]["revision"], c_write["result"]["revision"]
        need(created["index"] < b_write["index"] < c_write["index"],
             f"{task_id}: source write order")
        validations = [e for e in events if e["action"] == "validate"
                       and e["args"] == {"handle": source}
                       and e["result"].get("ok") is True
                       and e["result"]["revision"] == b_revision
                       and b_write["index"] < e["index"] < c_write["index"]]
        need(len(validations) == 1, f"{task_id}: validate source B before C")
        b_token = validations[0]["result"]["token"] if len(validations) == 1 else None
        publications = [e for e in events if e["action"] == "activate"
                        and e["result"].get("ok") is True
                        and e["args"].get("token") == b_token
                        and e["result"].get("published_revision") == b_revision
                        and e["result"].get("published_value") == validated
                        and e["index"] > c_write["index"]]
        need(len(publications) == 1, f"{task_id}: activate validated B after C")
        preserved = [e for e in events if e["action"] in {"fork", "snapshot"}
                     and e["args"] == {"handle": source}
                     and e["result"].get("ok") is True
                     and created["index"] < e["index"] < b_write["index"]
                     and e["result"].get("revision") == original_revision]
        good_backups = []
        for event in preserved:
            handle = event["result"]["handle"]
            if handle in terminal["handles"]:
                cell = terminal["cells"][terminal["handles"][handle]]
                if cell == {"revision": original_revision, "value": initial}:
                    good_backups.append(handle)
        need(len(good_backups) > 0, f"{task_id}: retain original exact A revision")
        source_cell = terminal["cells"].get(terminal["handles"].get(source))
        need(source_cell == {"revision": c_revision, "value": advanced},
             f"{task_id}: final source exact C revision")
        components.append({"id": task_id, "source": source,
                           "original_revision": original_revision,
                           "validated_revision": b_revision, "advanced_revision": c_revision,
                           "backups": good_backups, "token": b_token,
                           "publish_index": publications[0]["index"] if publications else None,
                           "validated_value": validated, "initial_value": initial})
    if len(components) != len(tasks):
        errors.append("program missing completed component")
    elif kind == "paired_publish":
        left, right = components
        need(left["source"] != right["source"], "paired components must have distinct sources")
        need(left["publish_index"] is not None and right["publish_index"] is not None
             and left["publish_index"] < right["publish_index"], "paired publication order")
    if components:
        last = components[-1]
        if kind == "rollback":
            first = components[0]
            rollback_tokens = {t for t, value in terminal["tokens"].items()
                               if value["created_handle"] in first["backups"]
                               and value["revision"] == first["original_revision"]
                               and value["value"] == first["initial_value"]}
            rollbacks = [e for e in events if e["action"] == "activate"
                         and e["result"].get("ok") is True
                         and e["args"].get("token") in rollback_tokens
                         and e["args"].get("handle") in first["backups"]
                         and first["publish_index"] is not None
                         and e["index"] > first["publish_index"]
                         and e["result"].get("published_revision") == first["original_revision"]
                         and e["result"].get("published_value") == first["initial_value"]]
            need(len(rollbacks) == 1, "rollback must publish B then validated original A")
            end_index = rollbacks[0]["index"] if rollbacks else None
            target_revision, target_value = first["original_revision"], first["initial_value"]
        else:
            end_index = last["publish_index"]
            target_revision, target_value = last["validated_revision"], last["validated_value"]
        if end_index is not None:
            live = states[end_index]["live"]
            need(live is not None and live["revision"] == target_revision
                 and live["value"] == target_value, "program exit live version")
        else:
            errors.append("program has no successful terminal publication")
    return {"id": program.get("id"), "pass": not errors,
            "errors": errors, "components": components}


def _policy_costs(portfolio: dict) -> dict:
    components = sum(len(p["components"]) for p in portfolio["programs"])
    overhead = 5 * sum(p["kind"] == "rollback" for p in portfolio["programs"])
    return {"safe": 17 * components + overhead,
            "fork": 6 + 15 * components + overhead,
            "full": 11 + 14 * components + overhead,
            "online": 5 + 14 * components + overhead}




def _online_facts(replay: dict, portfolio: dict) -> dict:
    """Infer both facts only from charged first-task responses."""
    events = replay["events"]
    _require(len(events) >= 9, "online learning calls missing")
    task = portfolio["programs"][0]["components"][0]
    _equal([e["action"] for e in events[:6]],
           ["create", "snapshot", "fork", "write", "read", "validate"],
           "online observation prefix")
    _equal(events[0]["args"], {"value": task["initial"]}, "online initial value")
    observed = events[4]["result"].get("value")
    _require(observed in {task["initial"], task["validated"]}, "online fork observation")
    fork = "copy" if observed == task["initial"] else "alias"
    publication = events[8]["result"]
    if publication.get("ok") is True:
        _require(publication.get("published_value") == task["validated"],
                 "online probe published validated value")
        activation = "pinned"
    else:
        _equal(publication, {"ok": False, "error": "token_revision_mismatch"},
               "online activation observation")
        activation = "live"
    return {"fork_mode": fork, "activation_mode": activation}


def _online_component(component: dict, task: dict, facts: dict) -> None:
    trace = component["trace"]
    _require(component.get("online_learning") is True, "first online learning marker")
    _equal(component.get("knowledge"), {"fork_mode": "unknown", "activation_mode": "unknown"},
           "online initial knowledge")
    _equal(component.get("learned_knowledge"), facts, "online earned knowledge")
    protection = "fork" if facts["fork_mode"] == "copy" else "snapshot"
    phases = [("initial", "create"), ("preserve_initial", "snapshot"),
              ("learn_fork_branch", "fork"), ("prepare_validated", "write"),
              ("learn_fork_read", "read"), ("validate", "validate"),
              ("preserve_validated", protection), ("advance_source", "write"),
              ("publish_probe", "activate")]
    if facts["activation_mode"] == "live":
        phases.append(("publish", "activate"))
    _equal([[e.get("phase"), e.get("action")] for e in trace],
           [list(pair) for pair in phases], "registered online knowledge-driven plan")
    source, backup = trace[0]["result"]["handle"], trace[1]["result"]["handle"]
    branch, token = trace[2]["result"]["handle"], trace[5]["result"]["token"]
    target = trace[6]["result"]["handle"]
    expected = [{"value": task["initial"]}, {"handle": source}, {"handle": source},
                {"handle": source, "value": task["validated"]}, {"handle": branch},
                {"handle": source}, {"handle": source},
                {"handle": source, "value": task["next_value"]},
                {"handle": source, "token": token}]
    if facts["activation_mode"] == "live":
        expected.append({"handle": target, "token": token})
    _equal([e["args"] for e in trace], expected, "online causal observations and inputs")
    _equal(component.get("handles"), {"source": source, "backup": backup, "target": target},
           "online reported roles")
    _equal(component.get("token"), token, "online reported token")
    _equal(component.get("publication"), trace[-1]["result"], "online reported publication")

def _standard_component(component: dict, task: dict, facts: dict) -> None:
    trace = component["trace"]
    _equal(component.get("knowledge"), facts, "component knowledge binding")
    protection = "fork" if facts["fork_mode"] == "copy" else "snapshot"
    phases = [("initial", "create"), ("preserve_initial", protection),
              ("prepare_validated", "write"), ("validate", "validate")]
    if facts["activation_mode"] != "pinned":
        phases.append(("preserve_validated", protection))
    phases.extend([("advance_source", "write"), ("publish", "activate")])
    _equal([[e.get("phase"), e.get("action")] for e in trace],
           [list(pair) for pair in phases], "registered knowledge-driven task plan")
    source, backup = trace[0]["result"]["handle"], trace[1]["result"]["handle"]
    token = trace[3]["result"]["token"]
    target = source if facts["activation_mode"] == "pinned" else trace[4]["result"]["handle"]
    _equal(component.get("handles"), {"source": source, "backup": backup, "target": target},
           "reported task roles")
    _equal(component.get("token"), token, "reported task token")
    _equal(component.get("publication"), trace[-1]["result"], "reported publication")
    wanted_args = [{"value": task["initial"]}, {"handle": source},
                   {"handle": source, "value": task["validated"]}, {"handle": source}]
    if facts["activation_mode"] != "pinned":
        wanted_args.append({"handle": source})
    wanted_args.extend([{ "handle": source, "value": task["next_value"]},
                        {"handle": target, "token": token}])
    _equal([e["args"] for e in trace], wanted_args, "registered task inputs/barriers")

def _check_execution_traces(executions: list, portfolio: dict,
                            task_replay: dict, execution_error: Any, facts: dict,
                            online: bool = False) -> None:
    _require(type(executions) is list, "execution list")
    programs = portfolio["programs"]
    _require(len(executions) <= len(programs), "extra executed program")
    flat = []
    for index, execution in enumerate(executions):
        program = programs[index]
        _equal(execution.get("id"), program["id"], "execution program id/order")
        _equal(execution.get("kind"), program["kind"], "execution program kind")
        parts = execution.get("components")
        _require(type(parts) is list and len(parts) <= len(program["components"]),
                 "execution component count")
        for component, task in zip(parts, program["components"]):
            _equal(component.get("task_id"), task["id"], "execution component id/order")
            trace = component.get("trace")
            _require(type(trace) is list, "component trace")
            is_first_online = online and index == 0 and task["id"] == programs[0]["components"][0]["id"]
            if is_first_online:
                _online_component(component, task, facts)
            else:
                _require(component.get("online_learning") is not True,
                         "online learning only in first component")
                _standard_component(component, task, facts)
            for entry in trace:
                _require(type(entry) is dict and set(entry) == {"phase", "action", "args", "result"}
                         and type(entry["phase"]) is str, "execution trace fields")
                flat.append({k: entry[k] for k in ("action", "args", "result")})
        rollback = execution.get("rollback")
        _require(type(rollback) is list, "rollback trace")
        if rollback:
            _require(program["kind"] == "rollback" and len(parts) == 1,
                     "rollback only in registered rollback program")
            _equal([[e.get("phase"), e.get("action")] for e in rollback],
                   [["rollback_validate", "validate"], ["rollback_activate", "activate"]],
                   "registered rollback plan")
            backup = parts[0]["handles"]["backup"]
            _equal([e["args"] for e in rollback], [{"handle": backup},
                   {"handle": backup, "token": rollback[0]["result"]["token"]}],
                   "registered rollback inputs")
        elif program["kind"] == "rollback" and execution_error is None:
            raise AuditError("missing rollback actions")
        for entry in rollback:
            _require(type(entry) is dict and set(entry) == {"phase", "action", "args", "result"}
                     and type(entry["phase"]) is str, "rollback trace fields")
            flat.append({k: entry[k] for k in ("action", "args", "result")})
        if execution_error is None:
            _require(len(parts) == len(program["components"]), "missing completed component")
    authoritative = [{k: e[k] for k in ("action", "args", "result")}
                     for e in task_replay["events"]]
    _equal(flat, authoritative, "complete planner trace versus service calls")
    if execution_error is None:
        _require(len(executions) == len(programs), "missing program without execution error")
        allowed_error = 9 if online and facts["activation_mode"] == "live" else None
        _require(all(e["result"].get("ok") is True or (
                     e["index"] == allowed_error and e["action"] == "activate" and
                     e["result"] == {"ok": False, "error": "token_revision_mismatch"})
                     for e in task_replay["events"]),
                 "failed task call without execution error or registered online probe")
    else:
        _require(type(execution_error) is dict and type(execution_error.get("type")) is str
                 and type(execution_error.get("message")) is str and executions,
                 "execution error metadata")
        _equal(execution_error.get("program_id"), executions[-1]["id"],
               "failed program binding")
        _require(bool(authoritative) and authoritative[-1]["action"] == "activate"
                 and authoritative[-1]["result"] == {"ok": False,
                                                       "error": "token_revision_mismatch"},
                 "halt requires logged nonmutating activation mismatch")
        _equal(executions[-1].get("error"), execution_error["message"],
               "partial program error description")
        if executions[-1]["components"] and not executions[-1]["rollback"]:
            _equal(executions[-1]["components"][-1].get("error"),
                   authoritative[-1]["result"], "partial task logged error")


def audit_episode(record: dict, portfolio: dict, expected_backend: str,
                  expected_strategy: str, protocol_sha: str) -> dict:
    """Check metadata, charged learning, transition replay and physical goals.

    `portfolio`, `expected_backend`, `expected_strategy` and `protocol_sha` must
    come from the frozen harness plan, never from untrusted record fields.
    An ablation may be an intact execution which fails its task goal: integrity
    and goal success are reported separately.
    """
    result = {"integrity_pass": False, "goal_pass": False, "pass": False,
              "cost": None, "errors": [], "programs": []}
    try:
        _require(type(record) is dict and type(portfolio) is dict, "record/portfolio type")
        _equal(record.get("schema"), "qkf.run27.record.v1", "record schema")
        _equal(record.get("portfolio_id"), portfolio["id"], "portfolio binding")
        _equal(record.get("portfolio_sha256"), _hash(portfolio), "public input digest")
        binding = {"portfolio_id": portfolio["id"], "portfolio_sha256": _hash(portfolio),
                   "backend": expected_backend, "strategy": expected_strategy}
        _equal(record.get("episode_id"), "ep_" + _hash(binding)[:20], "episode identity")
        _equal(record.get("backend"), expected_backend, "backend binding")
        _equal(record.get("strategy"), expected_strategy, "strategy binding")
        _equal(record.get("protocol_sha"), protocol_sha, "protocol binding")
        _require(type(protocol_sha) is str and len(protocol_sha) == 64,
                 "expected protocol hash")
        _require(type(portfolio["program_count"]) is int
                 and portfolio["program_count"] == len(portfolio["programs"]),
                 "public portfolio count")
        _equal(record.get("interface_scope"),
               {"model": "qkf.artifact.logical.v1", "portfolio_id": portfolio["id"]},
               "interface scope binding")
        arms = {"safe", "oracle", "ordinary_fork", "ordinary_full", "ordinary_best",
                "oracle_wrong_fork", "oracle_wrong_activation", "ordinary_online"}
        _require(expected_strategy in arms, "unregistered expected strategy")
        services = record.get("services")
        _require(type(services) is dict and set(services) == {"probe", "task"},
                 "registered services")
        task_replay = replay_service(services["task"], expected_backend)
        costs = _policy_costs(portfolio)
        selected = min(costs, key=costs.get)
        expected_policy = {"safe": "safe", "oracle": "oracle", "ordinary_fork": "fork",
                           "ordinary_full": "full", "ordinary_best": selected,
                           "ordinary_online": "online",
                           "oracle_wrong_fork": "oracle_wrong_fork",
                           "oracle_wrong_activation": "oracle_wrong_activation"}[expected_strategy]
        policy = record.get("policy")
        _require(type(policy) is dict, "policy metadata")
        _equal(policy.get("chosen"), expected_policy, "public budget policy choice")
        _equal(policy.get("predicted_costs"), costs, "registered ex ante cost estimates")
        probe_replay = None
        if expected_policy in {"fork", "full"}:
            _require(services["probe"] is not None, "charged probe missing")
            probe_replay = replay_service(services["probe"], expected_backend)
            facts = _probe_knowledge(probe_replay, expected_policy)
            source = "charged_probe_" + expected_policy
        else:
            _require(services["probe"] is None, "unregistered probe service")
            if expected_policy == "online":
                facts = _online_facts(task_replay, portfolio)
                source = "charged_task_observations"
            elif expected_policy == "safe":
                facts = {"fork_mode": "unknown", "activation_mode": "unknown"}
                source = "safe"
            else:
                facts = _true_knowledge(expected_backend)
                source = "oracle"
                if expected_policy == "oracle_wrong_fork":
                    facts["fork_mode"] = "alias" if facts["fork_mode"] == "copy" else "copy"
                    source = "oracle_ablation_fork"
                elif expected_policy == "oracle_wrong_activation":
                    facts["activation_mode"] = "live" if facts["activation_mode"] == "pinned" else "pinned"
                    source = "oracle_ablation_activation"
        _equal(record.get("knowledge"), {**facts, "source": source},
               "earned or registered oracle knowledge")
        total = task_replay["cost"] + (probe_replay["cost"] if probe_replay else 0)
        _require(type(record.get("total_cost")) is int and record["total_cost"] == total,
                 "full cost including sandbox probes")
        result["cost"] = total
        _check_execution_traces(record.get("executions"), portfolio, task_replay,
                                record.get("execution_error"), facts, expected_policy == "online")
        _equal(services["task"]["seed"], portfolio["id"] + ":task", "registered task seed")
        if probe_replay is not None:
            _equal(services["probe"]["seed"], portfolio["id"] + ":probe", "registered probe seed")
        probe_trace = record.get("probe_trace")
        _require(type(probe_trace) is list, "probe trace metadata")
        authoritative_probe = [{k: e[k] for k in ("action", "args", "result")}
                               for e in probe_replay["events"]] if probe_replay else []
        _equal([{k: e[k] for k in ("action", "args", "result")} for e in probe_trace],
               authoritative_probe, "complete probe trace versus charged calls")
        result["integrity_pass"] = True
        result["programs"] = [_program_goals(p, task_replay) for p in portfolio["programs"]]
        result["goal_pass"] = (record.get("execution_error") is None
                               and all(p["pass"] for p in result["programs"]))
        # The final live version must also equal the final program's terminal
        # publication, so an extra later activation cannot escape phase checks.
        if result["goal_pass"] and result["programs"]:
            last_program = portfolio["programs"][-1]
            last = result["programs"][-1]["components"][-1]
            revision = last["original_revision"] if last_program["kind"] == "rollback" else last["validated_revision"]
            value = last["initial_value"] if last_program["kind"] == "rollback" else last["validated_value"]
            live = task_replay["state"]["live"]
            if live is None or live["revision"] != revision or live["value"] != value:
                result["goal_pass"] = False
                result["errors"].append("final live version differs from final program goal")
        for checked in result["programs"]:
            result["errors"].extend(f'{checked["id"]}: {e}' for e in checked["errors"])
        if record.get("execution_error") is not None:
            result["errors"].append("registered task execution halted")
        result["task_cost"] = task_replay["cost"]
        result["probe_cost"] = probe_replay["cost"] if probe_replay else 0
        result["task_calls"] = task_replay["calls"]
        result["probe_calls"] = probe_replay["calls"] if probe_replay else 0
    except (AuditError, KeyError, TypeError, ValueError, IndexError) as exc:
        result["errors"].append(str(exc))
    result["pass"] = result["integrity_pass"] and result["goal_pass"]
    return result
