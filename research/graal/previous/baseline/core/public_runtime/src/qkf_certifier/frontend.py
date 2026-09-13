"""Fail-closed textual frontend for a documented, straight-line transfer MLIR subset.
Includes typed calls, actual returns, and explicit external definitions. Not full MLIR.
"""

import re

from .errors import InvalidInput, ResourceLimit, Unsupported
from .limits import (
    MAX_CALL_DEPTH,
    MAX_CALLS,
    MAX_DEPTH,
    MAX_FILES,
    MAX_FUNCTIONS,
    MAX_OPERATIONS,
    MAX_SOURCE_BYTES,
    MAX_TREE_NODES,
)

INTEGER_TYPE = "!transfer.integer"
A = "!transfer.abs_value<[!transfer.integer,!transfer.integer]>"
B = "i1"
V = r"%[A-Za-z0-9_]+"
N = r"[A-Za-z_][A-Za-z0-9_]*"

UNARY = set(
    "countl_one countl_zero countr_one countr_zero clear_sign_bit set_sign_bit neg get_bit_width get_all_ones".split()
)
BINARY = set(
    "and or xor add sub mul smax smin umin umax set_high_bits set_low_bits clear_high_bits clear_low_bits shl lshr ashr urem srem udiv sdiv".split()
)


def split_top(s):
    if not s:
        return []
    out = []
    start = 0
    depth = 0
    quoted = False
    for i, c in enumerate(s):
        if c == '"':
            quoted = not quoted
        if quoted:
            continue
        if c in "<[(":
            depth += 1
        if c in ">])" and not (c == ">" and i and s[i - 1] == "-"):
            depth -= 1
        if c == "," and depth == 0:
            out.append(s[start:i])
            start = i + 1
        if depth < 0:
            raise Unsupported("unbalanced syntax")
    if depth or quoted:
        raise Unsupported("unbalanced syntax")
    return out + [s[start:]]


def attributes(s):
    if not s:
        return {}
    d = {}
    if not s.startswith("{") or not s.endswith("}"):
        raise Unsupported("attributes")
    for field in split_top(s[1:-1]):
        k, sep, v = field.partition("=")
        if not re.fullmatch(N, k) or k in d:
            raise Unsupported("attribute key")
        d[k] = v if sep else None
    return d


def compact_lines(source):
    token = r'"[^"\n]*"|[%!@]?[A-Za-z_][A-Za-z_0-9.]*|[0-9]+|->|[^\s]'
    lines = []
    for raw in source.splitlines():
        # MLIR line comments, respecting quoted strings; escaped strings remain
        # outside the deliberately small attribute grammar.
        quoted = False
        for index, char in enumerate(raw):
            if char == '"' and (index == 0 or raw[index - 1] != "\\"):
                quoted = not quoted
            if not quoted and raw[index : index + 2] == "//":
                raw = raw[:index]
                break
        c = re.sub(r"\s+", "", raw).replace("i1attributes{", "i1 attributes{")
        if re.findall(token, raw) != re.findall(token, c):
            raise Unsupported("whitespace changes tokens")
        if c:
            lines.append(c)
    return lines


def generic_external(lines):
    # Actual pinned meet/top helpers use the generic function envelope.
    if len(lines) < 5 or lines[0] != '"func.func"()({':
        raise Unsupported("generic envelope")
    m = re.fullmatch(r"\^bb0\((.+)\):", lines[1])
    if not m:
        raise Unsupported("external block")
    argstr = m[1]
    args = split_top(argstr)
    types = []
    for a in args:
        ma = re.fullmatch("(" + V + r"):(.+)", a)
        if not ma or ma[2] != A:
            raise Unsupported("external args")
        types.append(ma[2])
    m = re.fullmatch(
        r"\}\)\{function_type=\((.*)\)->" + re.escape(A) + r',sym_name="(' + N + r')"\}:\(\)->\(\)',
        lines[-1],
    )
    if not m or split_top(m[1]) != types:
        raise Unsupported("external type")
    body = lines[2:-1]
    ret = re.fullmatch(r'"func.return"\((' + V + r")\):\(" + re.escape(A) + r"\)->\(\)", body[-1])
    if not ret:
        raise Unsupported("external return")
    body[-1] = "func.return" + ret[1] + ":" + A
    return ["func.func@" + m[2] + "(" + argstr + ")->" + A + "{"] + body + ["}"]


def parse_bundle(bundle):
    if (
        not isinstance(bundle, dict)
        or not bundle
        or any(not isinstance(k, str) or not k or not isinstance(v, str) for k, v in bundle.items())
    ):
        raise InvalidInput("sources must be a nonempty mapping of labels to UTF-8 text")
    if (
        len(bundle) > MAX_FILES
        or sum(len(v.encode("utf-8")) for v in bundle.values()) > MAX_SOURCE_BYTES
    ):
        raise ResourceLimit("source bundle exceeds size or file-count limit")
    funcs = {}
    operation_count = 0
    for label, source in sorted(bundle.items()):
        lines = compact_lines(source)
        if len(lines) >= 2 and lines[0] == "builtin.module{" and lines[-1] == "}":
            lines = lines[1:-1]
        elif lines and lines[0] == '"func.func"()({':
            lines = generic_external(lines)
        else:
            raise Unsupported("module/function envelope: " + label)
        cur = None
        for line in lines:
            if cur is None:
                m = re.fullmatch(
                    r"func.func@("
                    + N
                    + r")\((.*)\)->("
                    + re.escape(A)
                    + r"|i1)(?: ?attributes(\{.*\}))?\{",
                    line,
                )
                if not m:
                    raise Unsupported("function signature: " + line[:100])
                name, argstr, out, at = m.groups()
                args = []
                types = {}
                for a in split_top(argstr):
                    ma = re.fullmatch("(" + V + r"):(.+)", a)
                    if not ma or ma[2] != A or ma[1] in types:
                        raise Unsupported("argument signature")
                    args.append(ma[1])
                    types[ma[1]] = A
                if len(args) not in (1, 2) or name in funcs:
                    raise Unsupported("duplicate/arity")
                d = attributes(at)
                if set(d) - {"applied_to", "CPPCLASS", "is_forward", "from_weighted_dsl", "number"}:
                    raise Unsupported("function attribute")
                for k, val in d.items():
                    ok = (
                        (
                            k in ("applied_to", "CPPCLASS")
                            and bool(re.fullmatch(r'\["[A-Za-z0-9_.:]+"\]', val or ""))
                        )
                        or (k == "is_forward" and val == "true")
                        or (k == "from_weighted_dsl" and val is None)
                        or (k == "number" and bool(re.fullmatch(r'"[0-9_]+"', val or "")))
                    )
                    if not ok:
                        raise Unsupported("function attribute value")
                if len(funcs) >= MAX_FUNCTIONS:
                    raise ResourceLimit("function limit exceeded")
                cur = {
                    "args": args,
                    "out": out,
                    "ops": [],
                    "calls": [],
                    "return": None,
                    "source": label,
                }
                funcs[name] = cur
                continue
            if line == "}":
                if cur["return"] is None:
                    raise Unsupported("missing return")
                cur = None
                continue
            if cur["return"] is not None:
                raise Unsupported("statement after return")
            m = re.fullmatch(r"func.return(" + V + r"):(.+)", line)
            if m:
                if m[2] != cur["out"] or types.get(m[1]) != cur["out"]:
                    raise Unsupported("return type/SSA")
                cur["return"] = m[1]
                continue
            m = re.fullmatch("(" + V + r")=func.call@(" + N + r")\(([^()]*)\):\((.*)\)->(.+)", line)
            meta = None
            if m:
                dst, meta, argstr, sig, out = m.groups()
                args = split_top(argstr)
                ins = split_top(sig)
                op = "call"
                cur["calls"].append((meta, out))
                if any(t != A for t in ins) or out not in (A, B):
                    raise Unsupported("call signature")
            else:
                m = re.fullmatch(
                    "(" + V + r')="transfer\.(' + N + r')"\(([^()]*)\)(\{[^{}]*\})?:\((.*)\)->(.+)',
                    line,
                )
                ar = re.fullmatch(
                    "(" + V + r")=arith\.(andi|ori|xori)(" + V + "),(" + V + r")(\{.*\})?:i1", line
                )
                if ar:
                    dst, op, a, b, attr = ar.groups()
                    args = [a, b]
                    ins = [B, B]
                    out = B
                    d = attributes(attr)
                    op = "bool" + op[:-1]
                    expected = B
                elif m:
                    dst, op, argstr, attr, sig, out = m.groups()
                    args = split_top(argstr)
                    d = attributes(attr)
                    if op == "get":
                        ins = [A]
                        expected = INTEGER_TYPE
                    elif op == "make":
                        ins = [INTEGER_TYPE, INTEGER_TYPE]
                        expected = A
                    elif op == "cmp":
                        ins = [INTEGER_TYPE, INTEGER_TYPE]
                        expected = B
                    elif op == "select":
                        ins = [B, INTEGER_TYPE, INTEGER_TYPE]
                        expected = INTEGER_TYPE
                    elif op == "constant" or op in UNARY:
                        ins = [INTEGER_TYPE]
                        expected = INTEGER_TYPE
                    elif op in BINARY:
                        ins = [INTEGER_TYPE, INTEGER_TYPE]
                        expected = INTEGER_TYPE
                    else:
                        raise Unsupported("operation " + op)
                    if split_top(sig) != ins:
                        raise Unsupported("operation signature " + op)
                else:
                    raise Unsupported("statement " + line[:100])
                allowed = {"ret_type", "input_type"}
                if op == "get":
                    allowed.add("index")
                if op == "constant":
                    allowed.add("value")
                if op == "cmp":
                    allowed.add("predicate")
                if set(d) - allowed or out != expected:
                    raise Unsupported("operation attribute/result")
                if "ret_type" in d and d["ret_type"] not in (
                    {'"int"', '"bint"'}
                    if out == INTEGER_TYPE
                    else {'"bool"'}
                    if out == B
                    else set()
                ):
                    raise Unsupported("ret_type")
                if "input_type" in d:
                    v = d["input_type"]
                    if not v or not (v.startswith("[") and v.endswith("]")):
                        raise Unsupported("input_type")
                    labels = split_top(v[1:-1])
                    if len(labels) != len(ins) or any(
                        label_text
                        not in (
                            {'"int"', '"bint"'}
                            if t == INTEGER_TYPE
                            else {'"bool"'}
                            if t == B
                            else set()
                        )
                        for label_text, t in zip(labels, ins)
                    ):
                        raise Unsupported("input_type")
                for k in ("index", "value", "predicate"):
                    if k in allowed:
                        ma = re.fullmatch(r"(-?[0-9]+):index", d.get(k) or "")
                        if not ma:
                            raise Unsupported("missing numeric attribute")
                        if len(ma[1]) > 80:
                            raise ResourceLimit("numeric literal exceeds 256-bit limit")
                        meta = int(ma[1])
                        if meta.bit_length() > 256:
                            raise ResourceLimit("numeric literal exceeds 256-bit limit")
                if op == "get" and meta not in (0, 1):
                    raise Unsupported("get index")
                if op == "cmp" and meta not in range(10):
                    raise Unsupported("predicate")
            if len(args) != len(ins) or any(types.get(a) != t for a, t in zip(args, ins)):
                raise Unsupported("operand type/SSA")
            if dst in types:
                raise Unsupported("duplicate SSA")
            operation_count += 1
            if operation_count > MAX_OPERATIONS:
                raise ResourceLimit("operation limit exceeded")
            types[dst] = out
            cur["ops"].append((dst, op, args, meta))
        if cur is not None:
            raise Unsupported("unclosed function")
    checked = set()

    def visit(name, stack):
        if len(stack) > MAX_CALL_DEPTH:
            raise ResourceLimit("call depth limit exceeded")
        if name not in funcs or name in stack:
            raise Unsupported("unknown/recursive call " + name)
        if name in checked:
            return
        f = funcs[name]
        for callee, out in f["calls"]:
            if callee not in funcs or funcs[callee]["out"] != out:
                raise Unsupported("callee result declaration")
        for dst, op, args, meta in f["ops"]:
            if op == "call":
                visit(meta, stack + [name])
                # Each call output is checked again against the declared callee type.
                if len(args) != len(funcs[meta]["args"]):
                    raise Unsupported("callee arity")
        checked.add(name)

    for name in funcs:
        visit(name, [])
    # Check call result declarations by retaining actual uses via a second typed walk.
    for f in funcs.values():
        ts = dict.fromkeys(f["args"], A)
        for dst, op, args, meta in f["ops"]:
            if op == "call":
                t = funcs[meta]["out"]
                need = [A] * len(args)
            elif op == "get":
                t = INTEGER_TYPE
                need = [A]
            elif op == "make":
                t = A
                need = [INTEGER_TYPE, INTEGER_TYPE]
            elif op.startswith("bool"):
                t = B
                need = [B, B]
            elif op == "cmp":
                t = B
                need = [INTEGER_TYPE, INTEGER_TYPE]
            elif op == "select":
                t = INTEGER_TYPE
                need = [B, INTEGER_TYPE, INTEGER_TYPE]
            else:
                t = INTEGER_TYPE
                need = [INTEGER_TYPE] * len(args)
            if any(ts.get(a) != n for a, n in zip(args, need)):
                raise Unsupported("linked call type")
            ts[dst] = t
        if ts.get(f["return"]) != f["out"]:
            raise Unsupported("linked return type")
    return funcs


def expression(funcs, entry="solution"):
    if entry not in funcs or len(funcs[entry]["args"]) != 2:
        raise Unsupported("entry signature")
    # Limit expanded-tree size *before* recursive hashing or rewrite search.
    # Keep registered nodes alive so identity-based accounting cannot alias.
    metrics = {}
    retained = []
    calls = 0

    def register(e):
        if id(e) in metrics:
            return e
        child_indices = (
            () if e[0] in ("var", "zero", "ones", "width", "const") else range(1, len(e))
        )
        parts = [metrics[id(e[i])] for i in child_indices]
        depth = 1 + max((p[0] for p in parts), default=0)
        size = 1 + sum(p[1] for p in parts)
        if depth > MAX_DEPTH or size > MAX_TREE_NODES:
            raise ResourceLimit("expanded expression exceeds depth or node limit")
        metrics[id(e)] = (depth, size)
        retained.append(e)
        return e

    def run(name, values, depth=0):
        nonlocal calls
        calls += 1
        if depth > MAX_CALL_DEPTH or calls > MAX_CALLS:
            raise ResourceLimit("call expansion limit exceeded")
        f = funcs[name]
        env = dict(zip(f["args"], values))
        for dst, op, args, meta in f["ops"]:
            xs = [env[a] for a in args]
            if op == "call":
                e = run(meta, xs, depth + 1)
            elif op == "get":
                if xs[0][0] != "pair":
                    raise Unsupported("abstract projection")
                e = xs[0][meta + 1]
            elif op == "make":
                e = ("pair", *xs)
            elif op == "constant":
                e = ("zero",) if meta == 0 else ("ones",) if meta == -1 else ("const", meta)
            elif op == "get_bit_width":
                e = ("width",)
            elif op == "get_all_ones":
                e = ("ones",)
            elif op == "cmp":
                e = ("cmp" + str(meta), *xs)
            elif op == "neg":
                e = ("not", *xs)
            else:
                e = (op, *xs)
            env[dst] = register(e)
        return env[f["return"]]

    vs = [register(("var", i)) for i in range(4)]
    return run(entry, [register(("pair", vs[0], vs[1])), register(("pair", vs[2], vs[3]))])
