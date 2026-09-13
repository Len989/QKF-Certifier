"""Separate direct SSA word interpreter for regression. Shares only the frontend."""

import itertools


def operation(op, xs, meta, w):
    m = (1 << w) - 1
    if op == "get":
        return xs[0][meta]
    if op == "make":
        return tuple(xs)
    if op == "constant":
        return meta & m
    if op == "get_bit_width":
        return w
    if op == "get_all_ones":
        return m
    if op == "neg":
        return xs[0] ^ m
    if op == "select":
        return xs[1] if xs[0] else xs[2]
    if op.startswith("bool"):
        a, b = xs
        return (
            bool(a and b) if op == "booland" else bool(a or b) if op == "boolor" else bool(a != b)
        )

    def signed(x):
        return x - (1 << w) if x >> (w - 1) else x

    if op == "cmp":
        a, b = xs
        sa, sb = signed(a), signed(b)
        return [a == b, a != b, sa < sb, sa <= sb, sa > sb, sa >= sb, a < b, a <= b, a > b, a >= b][
            meta
        ]
    if op in ("countl_one", "countl_zero", "countr_one", "countr_zero"):
        n = 0
        desired = int(op.endswith("one"))
        positions = range(w - 1, -1, -1) if op.startswith("countl") else range(w)
        for i in positions:
            if ((xs[0] >> i) & 1) != desired:
                break
            n += 1
        return n
    if op == "clear_sign_bit":
        return xs[0] & ((1 << (w - 1)) - 1)
    if op == "set_sign_bit":
        return xs[0] | (1 << (w - 1))
    a, b = xs
    if op == "and":
        return a & b
    if op == "or":
        return a | b
    if op == "xor":
        return a ^ b
    if op == "add":
        return (a + b) & m
    if op == "sub":
        return (a - b) & m
    if op == "mul":
        return (a * b) & m
    if op == "umin":
        return min(a, b)
    if op == "umax":
        return max(a, b)
    if op == "smin":
        return min(a, b, key=signed)
    if op == "smax":
        return max(a, b, key=signed)
    if op in ("clear_low_bits", "clear_high_bits", "set_low_bits", "set_high_bits"):
        n = min(b, w)
        mask = (1 << n) - 1
        if op.endswith("high_bits"):
            mask <<= w - n
        return a | mask if op.startswith("set") else a & (mask ^ m)
    if op == "shl":
        return (a << b) & m if b < w else 0
    if op == "lshr":
        return a >> b if b < w else 0
    if op == "ashr":
        return (signed(a) >> min(b, w)) & m
    if op == "udiv":
        return a // b if b else m
    if op == "urem":
        return a % b if b else a
    sa, sb = signed(a), signed(b)
    if op == "sdiv":
        if not b:
            return 1 if sa < 0 else m
        q = abs(sa) // abs(sb)
        return (-q if (sa < 0) != (sb < 0) else q) & m
    if op == "srem":
        if not b:
            return a
        q = abs(sa) % abs(sb)
        return (-q if sa < 0 else q) & m
    raise ValueError(op)


def evaluate(funcs, inputs, w, entry="solution"):
    def run(name, values):
        f = funcs[name]
        env = dict(zip(f["args"], values))
        for dst, op, args, meta in f["ops"]:
            xs = [env[a] for a in args]
            env[dst] = run(meta, xs) if op == "call" else operation(op, xs, meta, w)
        return env[f["return"]]

    return run(entry, inputs)


def expr_value(e, values, w):
    op = e[0]
    if op == "var":
        return values[e[1]]
    if op == "zero":
        return 0
    if op == "ones":
        return (1 << w) - 1
    if op == "width":
        return w
    if op == "const":
        return e[1] & ((1 << w) - 1)
    if op in ("true", "false"):
        return op == "true"
    xs = [expr_value(x, values, w) for x in e[1:]]
    if op == "pair":
        return tuple(xs)
    if op == "not":
        return xs[0] ^ ((1 << w) - 1)
    if op.startswith("cmp"):
        return operation("cmp", xs, int(op[3:]), w)
    return operation(op, xs, None, w)


def kbwords(w):
    return [(z, o) for z in range(1 << w) for o in range(1 << w) if not z & o]


def gamma(k, w):
    return [x for x in range(1 << w) if not (x & k[0]) and x & k[1] == k[1]]


def exact_output(a, b, w, target):
    vals = [
        {"and": x & y, "or": x | y, "xor": x ^ y, "add": (x + y) & ((1 << w) - 1)}[target]
        for x, y in itertools.product(gamma(a, w), gamma(b, w))
    ]
    o = (1 << w) - 1
    may = 0
    for v in vals:
        o &= v
        may |= v
    return ((1 << w) - 1) ^ may, o


def sound_output(out, exact):
    return not (out[0] & ~exact[0]) and not (out[1] & ~exact[1])
