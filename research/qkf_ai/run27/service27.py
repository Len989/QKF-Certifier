"""Run27's independently specified, in-memory artifact-version service.

This is a synthetic logical service, not a filesystem, persistence layer, or
existing product API. Planners receive ``service.call`` only. Hidden backend
parameters never appear in a call result. The harness may inspect state/logs
after execution for independent replay.

Backend classes combine COPY/ALIAS fork semantics and PIN/LIVE activation:
PIN deploys the immutable version recorded by a validation token. LIVE requires
the supplied handle's current revision to equal the token's revision. Tokens
are reusable across handles; their original handle is provenance, not binding.
Every successful activation therefore deploys a previously validated version.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


COSTS = {
    "create": 2,
    "read": 1,
    "fork": 1,
    "snapshot": 3,
    "write": 2,
    "validate": 3,
    "activate": 2,
}
BACKENDS = {
    "copy_pin": ("copy", "pin"),
    "copy_live": ("copy", "live"),
    "alias_pin": ("alias", "pin"),
    "alias_live": ("alias", "live"),
}
_ARGUMENTS = {
    "create": {"value"},
    "read": {"handle"},
    "fork": {"handle"},
    "snapshot": {"handle"},
    "write": {"handle", "value"},
    "validate": {"handle"},
    "activate": {"handle", "token"},
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def state_sha256(state: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(state).encode("utf-8")).hexdigest()


class _RequestError(Exception):
    pass


class ArtifactService:
    """A fresh service instance with an empty state and charged request log.

    Handle/token identifiers depend on seed and counter, never backend class.
    The Python object itself is not an isolation sandbox: the evaluation harness
    must pass only its public call callback to the planner.
    """

    def __init__(self, backend: str, *, seed: str = "default") -> None:
        if backend not in BACKENDS:
            raise ValueError("unknown backend")
        if type(seed) is not str:
            raise TypeError("seed must be str")
        self._fork_mode, self._activation_mode = BACKENDS[backend]
        self._seed = seed
        self._state: dict[str, Any] = {
            "cells": {},
            "handles": {},
            "tokens": {},
            "live": None,
            "validated_revisions": [],
            "next_revision": 1,
            "next_handle": 1,
            "next_cell": 1,
            "next_token": 1,
        }
        self._log: list[dict[str, Any]] = []
        self._total_cost = 0

    @property
    def total_cost(self) -> int:
        return self._total_cost

    def export_state(self) -> dict[str, Any]:
        return copy.deepcopy(self._state)

    def export_log(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._log)

    def _identifier(self, namespace: str, counter: int) -> str:
        material = canonical_json([self._seed, namespace, counter])
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
        return f"{namespace}_{digest}"

    def _new_handle(self, cell: str) -> str:
        state = self._state
        handle = self._identifier("h", state["next_handle"])
        state["next_handle"] += 1
        state["handles"][handle] = cell
        return handle

    def _new_cell(self, revision: int, value: str) -> str:
        state = self._state
        cell = self._identifier("c", state["next_cell"])
        state["next_cell"] += 1
        state["cells"][cell] = {"revision": revision, "value": value}
        return cell

    def _cell_for(self, handle: str) -> dict[str, Any]:
        state = self._state
        if handle not in state["handles"]:
            raise _RequestError("unknown_handle")
        return state["cells"][state["handles"][handle]]

    @staticmethod
    def _check_arguments(action: str, args: dict[str, Any]) -> None:
        if action not in _ARGUMENTS:
            raise _RequestError("unknown_operation")
        if set(args) != _ARGUMENTS[action]:
            raise _RequestError("invalid_arguments")
        # Exact strings; booleans, bytes, numbers, collections and subclasses
        # have no accidental conversion to artifact values or identifiers.
        if any(type(value) is not str for value in args.values()):
            raise _RequestError("invalid_arguments")
        try:
            for value in args.values():
                value.encode("utf-8")
        except UnicodeEncodeError:
            raise _RequestError("invalid_arguments")

    def _dispatch(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        self._check_arguments(action, args)
        state = self._state
        if action == "create":
            revision = state["next_revision"]
            state["next_revision"] += 1
            cell = self._new_cell(revision, args["value"])
            handle = self._new_handle(cell)
            return {"ok": True, "handle": handle,
                    "revision": revision, "value": args["value"]}

        handle = args["handle"]
        cell = self._cell_for(handle)
        if action == "read":
            return {"ok": True, "revision": cell["revision"],
                    "value": cell["value"]}
        if action in {"fork", "snapshot"}:
            source_cell = state["handles"][handle]
            if action == "snapshot" or self._fork_mode == "copy":
                new_cell = self._new_cell(cell["revision"], cell["value"])
            else:
                new_cell = source_cell
            new_handle = self._new_handle(new_cell)
            return {"ok": True, "handle": new_handle,
                    "revision": cell["revision"], "value": cell["value"]}
        if action == "write":
            revision = state["next_revision"]
            state["next_revision"] += 1
            cell.update(revision=revision, value=args["value"])
            return {"ok": True, "revision": revision}
        if action == "validate":
            token = self._identifier("t", state["next_token"])
            state["next_token"] += 1
            state["tokens"][token] = {
                "created_handle": handle,
                "revision": cell["revision"],
                "value": cell["value"],
            }
            if cell["revision"] not in state["validated_revisions"]:
                state["validated_revisions"].append(cell["revision"])
                state["validated_revisions"].sort()
            return {"ok": True, "token": token, "revision": cell["revision"]}
        if action == "activate":
            token_id = args["token"]
            if token_id not in state["tokens"]:
                raise _RequestError("unknown_token")
            token = state["tokens"][token_id]
            if (self._activation_mode == "live"
                    and cell["revision"] != token["revision"]):
                raise _RequestError("token_revision_mismatch")
            # PIN uses the immutable token snapshot. LIVE has just established
            # equality to that exact revision, so the token snapshot agrees.
            published = token if self._activation_mode == "pin" else cell
            state["live"] = {
                "handle": handle,
                "token": token_id,
                "revision": published["revision"],
                "value": published["value"],
            }
            return {"ok": True, "published_revision": published["revision"],
                    "published_value": published["value"]}
        raise AssertionError("unreachable operation")

    def call(self, action: str, **args: Any) -> dict[str, Any]:
        """Perform one JSON request; errors are charged and state-preserving.

        JSON representability is a transport precondition, not a service action.
        Known actions cost their registered amount even with malformed args;
        unknown actions cost one. Log metadata is excluded from state hashes.
        """
        if type(action) is not str:
            raise TypeError("action must be str")
        # Detach input containers before logging and reject non-JSON transport.
        canonical_json(args).encode("utf-8")
        request_args = copy.deepcopy(args)
        before = self.export_state()
        charge = COSTS.get(action, 1)
        try:
            result = self._dispatch(action, request_args)
        except _RequestError as exc:
            # Explicit restoration also protects atomic error semantics when
            # a future action performs checks after an intermediate mutation.
            self._state = before
            result = {"ok": False, "error": str(exc)}
        self._total_cost += charge
        self._log.append({
            "index": len(self._log) + 1,
            "action": action,
            "args": request_args,
            "result": copy.deepcopy(result),
            "cost": charge,
            "total_cost": self._total_cost,
            "before_sha256": state_sha256(before),
            "after_sha256": state_sha256(self._state),
        })
        return copy.deepcopy(result)
