"""Trusted local rewrite rules and obligation checking. No normalization search here."""

import hashlib
import itertools
import json
from functools import lru_cache

from .certificate import SCHEMA, validate
from .errors import InvalidCertificate
from .frontend import Unsupported, expression, parse_bundle

Z = ("zero",)
T = ("ones",)
W = ("width",)
C1 = ("const", 1)
TRUE = ("true",)
FALSE = ("false",)
LEAVES = {"var", "zero", "ones", "width", "const", "true", "false"}
BIT = {"var", "zero", "ones", "and", "or", "xor", "not"}
KB = ((1, 0), (0, 1), (0, 0))
CONTRACT = "total-transfer-words-v2; positive-width; modular-arithmetic; SMT-total-div-shift; standard-counts; nonbottom-KB"


def children(e):
    return () if e[0] in LEAVES else tuple(range(1, len(e)))


def frozen(x):
    return tuple(frozen(a) for a in x) if isinstance(x, list) else x


def digest(x):
    return hashlib.sha256(json.dumps(x, separators=(",", ":")).encode()).hexdigest()


def hashes(bundle):
    return {k: hashlib.sha256(v.encode()).hexdigest() for k, v in sorted(bundle.items())}


@lru_cache(maxsize=100000)
def coordinate(e):
    return e[0] in BIT and all(coordinate(e[i]) for i in children(e))


def bit(e, values):
    op = e[0]
    if op == "var":
        return values[e[1]]
    if op == "zero":
        return 0
    if op == "ones":
        return 1
    if op == "not":
        return 1 ^ bit(e[1], values)
    a, b = (bit(x, values) for x in e[1:])
    if op == "and":
        return a & b
    if op == "or":
        return a | b
    if op == "xor":
        return a ^ b
    raise Unsupported("non-coordinate expression")


@lru_cache(maxsize=100000)
def disjoint(x, y):
    if coordinate(x) and coordinate(y):
        return all(not (bit(x, a + b) & bit(y, a + b)) for a, b in itertools.product(KB, repeat=2))
    if x[0] == "and":
        return disjoint(x[1], y) or disjoint(x[2], y)
    if y[0] == "and":
        return disjoint(x, y[1]) or disjoint(x, y[2])
    return False


@lru_cache(maxsize=100000)
def subset(x, y):
    if x == y or x == Z or y == T:
        return True
    if coordinate(x) and coordinate(y):
        return all(
            not (bit(x, a + b) & (1 ^ bit(y, a + b))) for a, b in itertools.product(KB, repeat=2)
        )
    return (y[0] == "or" and (subset(x, y[1]) or subset(x, y[2]))) or (
        x[0] == "and" and (subset(x[1], y) or subset(x[2], y))
    )


@lru_cache(maxsize=100000)
def lowbit(e):
    op = e[0]
    if e == Z:
        return 0
    if e == T:
        return 1
    if op == "const":
        return e[1] & 1
    if op == "shl" and e[2] == C1:
        return 0
    if op == "not":
        a = lowbit(e[1])
        return None if a is None else a ^ 1
    if op in ("and", "or", "xor", "add", "sub"):
        a, b = lowbit(e[1]), lowbit(e[2])
        if op == "and" and (a == 0 or b == 0):
            return 0
        if op == "or" and (a == 1 or b == 1):
            return 1
        if a is None or b is None:
            return None
        return a & b if op == "and" else a | b if op == "or" else a ^ b
    return None


RULES = (
    "idempotent",
    "self-cancel",
    "zero-and",
    "ones-or",
    "zero-identity",
    "ones-and",
    "not-constant",
    "not-not",
    "disjoint-and",
    "disjoint-add",
    "clear-width",
    "count-constant",
    "clear-zero-count",
    "set-zero-count",
    "set-leading-included",
    "umin-zero",
    "umax-ones",
    "remainder-zero",
    "urem-one",
    "udiv-one",
    "count-bound",
    "compare-reflexive",
    "compare-unsigned-bound",
    "select-constant",
    "select-same",
    "bool-constant",
    "set-low-one",
    "zero-shift",
    "shift-zero-count",
)


def apply_rule(rule, e):
    op = e[0]
    a = e[1] if len(e) > 1 else None
    b = e[2] if len(e) > 2 else None
    if rule == "idempotent" and op in ("and", "or", "smax", "smin", "umax", "umin") and a == b:
        return a
    if rule == "self-cancel" and op in ("xor", "sub") and a == b:
        return Z
    if rule == "zero-and" and op in ("and", "mul") and (a == Z or b == Z):
        return Z
    if rule == "ones-or" and op == "or" and (a == T or b == T):
        return T
    if rule == "zero-identity":
        if op in ("or", "xor", "add") and a == Z:
            return b
        if op in ("or", "xor", "add", "sub") and b == Z:
            return a
    if rule == "ones-and" and op == "and" and (a == T or b == T):
        return b if a == T else a
    if rule == "not-constant" and op == "not" and a in (Z, T):
        return T if a == Z else Z
    if rule == "not-not" and op == "not" and a[0] == "not":
        return a[1]
    if rule == "disjoint-and" and op == "and" and disjoint(a, b):
        return Z
    if rule == "disjoint-add" and op == "add" and disjoint(a, b):
        return ("or", a, b)
    if rule == "clear-width" and op in ("clear_low_bits", "clear_high_bits") and b == W:
        return Z
    if (
        rule == "count-constant"
        and op in ("countl_one", "countr_one", "countl_zero", "countr_zero")
        and a in (Z, T)
    ):
        return W if (op.endswith("one") and a == T) or (op.endswith("zero") and a == Z) else Z
    if rule == "clear-zero-count" and op in ("clear_low_bits", "clear_high_bits"):
        if b == Z:
            return a
        if a == Z:
            return Z
    if rule == "set-zero-count" and op in ("set_low_bits", "set_high_bits") and b == Z:
        return a
    if (
        rule == "set-leading-included"
        and op == "set_high_bits"
        and b[0] == "countl_one"
        and subset(b[1], a)
    ):
        return a
    if rule == "umin-zero" and op == "umin" and (a == Z or b == Z):
        return Z
    if rule == "umax-ones" and op == "umax" and (a == T or b == T):
        return T
    if rule == "remainder-zero" and op in ("urem", "srem") and a == Z:
        return Z
    if rule == "urem-one" and op == "urem" and b == C1:
        return Z
    if rule == "udiv-one" and op == "udiv" and b == C1:
        return a
    if (
        rule == "count-bound"
        and op in ("cmp6", "cmp9")
        and a == W
        and b[0] in ("countl_one", "countl_zero", "countr_one", "countr_zero")
    ):
        return FALSE if op == "cmp6" else TRUE
    if rule == "compare-reflexive" and op.startswith("cmp") and a == b:
        return TRUE if int(op[3:]) in (0, 3, 5, 7, 9) else FALSE
    if rule == "compare-unsigned-bound":
        if op == "cmp6" and (b == Z or a == T):
            return FALSE
        if op == "cmp7" and (a == Z or b == T):
            return TRUE
        if op == "cmp8" and (a == Z or b == T):
            return FALSE
        if op == "cmp9" and (b == Z or a == T):
            return TRUE
        if op == "cmp6" and a == Z and lowbit(b) == 1:
            return TRUE
        if op == "cmp8" and b == Z and lowbit(a) == 1:
            return TRUE
    if rule == "select-constant" and op == "select" and a in (TRUE, FALSE):
        return e[2] if a == TRUE else e[3]
    if rule == "select-same" and op == "select" and e[2] == e[3]:
        return e[2]
    if rule == "bool-constant" and op in ("booland", "boolor", "boolxor"):
        if a in (TRUE, FALSE) and b in (TRUE, FALSE):
            x, y = a == TRUE, b == TRUE
            r = x and y if op == "booland" else x or y if op == "boolor" else x != y
            return TRUE if r else FALSE
        if op == "booland" and (a == FALSE or b == FALSE):
            return FALSE
        if op == "boolor" and (a == TRUE or b == TRUE):
            return TRUE
    if rule == "set-low-one" and op == "set_low_bits" and a == Z and b == C1:
        return C1
    if rule == "zero-shift" and op in ("shl", "lshr", "ashr") and a == Z:
        return Z
    if rule == "shift-zero-count" and op in ("shl", "lshr", "ashr") and b == Z:
        return a
    raise ValueError("inapplicable rule " + rule)


def at(e, path):
    for i in path:
        if type(i) is not int or i not in children(e):
            raise ValueError("bad proof path")
        e = e[i]
    return e


def replace(e, path, new):
    if not path:
        return new
    i = path[0]
    if type(i) is not int or i not in children(e):
        raise ValueError("bad proof path")
    xs = list(e)
    xs[i] = replace(e[i], path[1:], new)
    return tuple(xs)


def table(e, target):
    if target not in ("and", "or", "xor"):
        raise Unsupported("no coordinatewise target contract")
    if e[0] != "pair" or not all(coordinate(x) for x in e[1:]):
        raise Unsupported("residual non-coordinate operations")

    def gamma(k):
        return {x for x in (0, 1) if not x & k[0] and x & k[1] == k[1]}

    rows = []
    for a, b in itertools.product(KB, repeat=2):
        out = tuple(bit(x, a + b) for x in e[1:])
        exact = {
            {"and": x & y, "or": x | y, "xor": x ^ y}[target]
            for x, y in itertools.product(gamma(a), gamma(b))
        }
        rows.append(
            {
                "a": list(a),
                "b": list(b),
                "out": list(out),
                "exact": sorted(exact),
                "sound": exact <= gamma(out),
                "optimal": exact == gamma(out),
            }
        )
    return rows


def replay(bundle, entry, certificate):
    validate(certificate)
    if (
        certificate.get("schema") != SCHEMA
        or certificate.get("sources") != hashes(bundle)
        or certificate.get("entry") != entry
        or certificate.get("semantics") != CONTRACT
    ):
        raise InvalidCertificate("source binding or semantics contract mismatch")
    e = expression(parse_bundle(bundle), entry)
    if certificate.get("initial_hash") != digest(e):
        raise InvalidCertificate("initial expression mismatch")
    for step in certificate["steps"]:
        if set(step) != {"path", "rule"} or step["rule"] not in RULES:
            raise InvalidCertificate("unknown proof instruction")
        path = step["path"]
        try:
            new = apply_rule(step["rule"], at(e, path))
            e = replace(e, path, new)
        except ValueError as exc:
            raise InvalidCertificate(str(exc)) from exc
    if e != frozen(certificate["normal_form"]):
        raise InvalidCertificate("normal form mismatch")
    return e


def check(bundle, target, certificate, entry="solution"):
    validate(certificate)
    if certificate.get("target") != target:
        raise InvalidCertificate("external target mismatch")
    e = replay(bundle, entry, certificate)
    rows = table(e, target)
    if certificate.get("rows") != rows:
        raise InvalidCertificate("table mismatch")
    bad = next((r for r in rows if not r["sound"]), None)
    return dict(
        status="unsound" if bad else "certified",
        all_positive_widths=not bool(bad),
        optimal=all(r["optimal"] for r in rows),
        witness=bad,
        semantics=CONTRACT,
        pinned_lowering_verified=False,
    )
