"""Strict dependency-free validation of the public certificate format."""

import json
import re

from .errors import InvalidCertificate, ResourceLimit
from .limits import MAX_CERTIFICATE_BYTES, MAX_DEPTH, MAX_FILES, MAX_STEPS, MAX_TREE_NODES

SCHEMA = "qkf-rewrite-v3"
LEAF_ARITY = {"var": 1, "const": 1, "zero": 0, "ones": 0, "width": 0, "true": 0, "false": 0}
UNARY = {
    "not",
    "countl_one",
    "countl_zero",
    "countr_one",
    "countr_zero",
    "clear_sign_bit",
    "set_sign_bit",
}
BINARY = {
    "pair",
    "and",
    "or",
    "xor",
    "add",
    "sub",
    "mul",
    "smax",
    "smin",
    "umax",
    "umin",
    "set_high_bits",
    "set_low_bits",
    "clear_high_bits",
    "clear_low_bits",
    "shl",
    "lshr",
    "ashr",
    "urem",
    "srem",
    "udiv",
    "sdiv",
    "booland",
    "boolor",
    "boolxor",
} | {"cmp" + str(i) for i in range(10)}


def _require(condition, reason):
    if not condition:
        raise InvalidCertificate(reason)


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidCertificate("duplicate JSON key: " + key)
        result[key] = value
    return result


def loads(text):
    """Parse a certificate with exact types and no duplicate keys or NaN."""
    if len(text.encode("utf-8")) > MAX_CERTIFICATE_BYTES:
        raise ResourceLimit("certificate exceeds byte limit")
    try:
        result = json.loads(
            text,
            object_pairs_hook=_no_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                InvalidCertificate("non-JSON numeric value: " + value)
            ),
        )
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, InvalidCertificate):
            raise
        raise InvalidCertificate("invalid certificate JSON") from exc
    validate(result)
    return result


def validate(c):
    _require(type(c) is dict, "certificate must be an object")
    required = {
        "schema",
        "sources",
        "entry",
        "semantics",
        "initial_hash",
        "steps",
        "normal_form",
        "target",
    }
    _require(required <= c.keys() and set(c) - required <= {"rows"}, "certificate fields mismatch")
    _require(c["schema"] == SCHEMA, "unsupported certificate version")
    _require(
        type(c["entry"]) is str and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", c["entry"]),
        "invalid entry",
    )
    _require(type(c["semantics"]) is str, "invalid semantics contract")
    _require(
        type(c["sources"]) is dict and 0 < len(c["sources"]) <= MAX_FILES, "invalid source bindings"
    )
    for label, sha in c["sources"].items():
        _require(
            type(label) is str
            and bool(label)
            and type(sha) is str
            and re.fullmatch(r"[0-9a-f]{64}", sha),
            "invalid source hash",
        )
    _require(
        type(c["initial_hash"]) is str and re.fullmatch(r"[0-9a-f]{64}", c["initial_hash"]),
        "invalid initial hash",
    )
    _require(
        c["target"] is None or type(c["target"]) is str and c["target"] in ("and", "or", "xor"),
        "unsupported certificate target",
    )
    _require(type(c["steps"]) is list, "steps must be an array")
    if len(c["steps"]) > MAX_STEPS:
        raise ResourceLimit("proof step limit exceeded")
    for step in c["steps"]:
        _require(type(step) is dict and set(step) == {"path", "rule"}, "invalid proof instruction")
        _require(
            type(step["path"]) is list
            and len(step["path"]) <= MAX_DEPTH
            and all(type(i) is int and 1 <= i <= 3 for i in step["path"]),
            "invalid proof path",
        )
        _require(type(step["rule"]) is str, "invalid rule name")
    pending = [(c["normal_form"], 0)]
    count = 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if count > MAX_TREE_NODES or depth > MAX_DEPTH:
            raise ResourceLimit("normal form complexity limit exceeded")
        _require(
            type(node) is list and bool(node) and type(node[0]) is str, "invalid expression node"
        )
        op = node[0]
        if op in LEAF_ARITY:
            _require(len(node) == LEAF_ARITY[op] + 1, "invalid leaf arity")
            if op in ("const", "var"):
                _require(type(node[1]) is int, "expression integer must not be a bool or float")
                _require(
                    0 <= node[1] <= 3 if op == "var" else node[1].bit_length() <= 256,
                    "expression integer out of range",
                )
        else:
            arity = 1 if op in UNARY else 2 if op in BINARY else 3 if op == "select" else None
            _require(arity is not None and len(node) == arity + 1, "unknown operation or arity")
            pending.extend((child, depth + 1) for child in node[1:])
    if c["target"] is None:
        _require("rows" not in c, "normalization certificate cannot carry target rows")
        return
    _require(
        "rows" in c and type(c["rows"]) is list and len(c["rows"]) == 9, "expected nine proof rows"
    )
    for row in c["rows"]:
        _require(
            type(row) is dict and set(row) == {"a", "b", "out", "exact", "sound", "optimal"},
            "invalid row fields",
        )
        for key in ("a", "b", "out"):
            value = row[key]
            _require(
                type(value) is list
                and len(value) == 2
                and all(type(x) is int and x in (0, 1) for x in value),
                "invalid mask pair",
            )
        _require(
            type(row["exact"]) is list
            and row["exact"] in ([0], [1], [0, 1])
            and all(type(x) is int for x in row["exact"]),
            "invalid concrete values",
        )
        _require(
            type(row["sound"]) is bool and type(row["optimal"]) is bool,
            "row verdict must be boolean",
        )
