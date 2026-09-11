import re

from qkf_certifier.frontend import INTEGER_TYPE, A, B


def variants(source):
    lines = source.splitlines()
    types = {}
    out = {}

    def add(name, i, new):
        ls = lines.copy()
        ls[i] = new
        out[name] = "\n".join(ls) + "\n"

    for i, line in enumerate(lines):
        if "func.func @" in line:
            types = dict.fromkeys(re.findall(r"(%\w+)\s*:\s*!transfer.abs_value", line), A)
            continue
        m = re.match(r'\s*(%\w+) = (?:"transfer\.(\w+)"|func.call @(\w+))\(([^)]*)\)', line)
        if m:
            dst, op, callee, argstr = m.groups()
            args = argstr.split(", ") if argstr else []
            for j, arg in enumerate(args):
                for replacement, typ in types.items():
                    if replacement == arg or types.get(arg) != typ:
                        continue
                    ys = args.copy()
                    ys[j] = replacement
                    add(
                        f"L{i + 1}:arg{j}:{replacement}",
                        i,
                        line[: m.start(4)] + ", ".join(ys) + line[m.end(4) :],
                    )
            if op in ("and", "or", "xor", "add", "sub"):
                for other in ("and", "or", "xor", "add", "sub"):
                    if other != op:
                        add(
                            f"L{i + 1}:op:{other}",
                            i,
                            line.replace('"transfer.' + op + '"', '"transfer.' + other + '"'),
                        )
            if op == "make" or callee:
                typ = A
            elif op == "cmp":
                typ = B
            else:
                typ = INTEGER_TYPE
            types[dst] = typ
        m = re.match(r"\s*func.return (%\w+)", line)
        if m:
            for replacement, typ in types.items():
                if replacement != m[1] and typ == types[m[1]]:
                    add(
                        f"L{i + 1}:return:{replacement}",
                        i,
                        line[: m.start(1)] + replacement + line[m.end(1) :],
                    )
    return out
