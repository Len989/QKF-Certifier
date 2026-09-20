"""Producer-only direct controls; no congruence closure or kernel saturation."""


def atoms(seeds):
    k, b, bc = seeds[7], seeds[2], seeds[6]
    return [k & (7 ^ bc), b, bc & (7 ^ b)]


def range_value(images, target):
    value = 0
    for i in range(3):
        if target & (1 << i):
            value |= images[i]
    return value


def direct_membership(output, nxt, y, target):
    return output == y and bool(target & (1 << nxt))


def action_cell(ctx, branches, target):
    result = 0
    for i, p in enumerate(branches):
        bit, nxt = p['result']
        if direct_membership(bit, nxt, ctx['request']['label'][3], target):
            result |= 1 << i
    return result
