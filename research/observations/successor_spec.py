"""Independent, versioned targets for a masked unsigned cyclic successor.

No source operation, carry state, producer or saved certificate is used here.
A legal word has all must bits and no bits outside may. Under the entry
contract must <=bits seed <=bits may, its least/greatest elements are must/may.
Three order observations and three Boolean flags suffice to check the target.
"""
from itertools import product

from .model import digest, integer, require

SCHEMA = "qkf-masked-successor-spec-v1"
RULES = "masked-extrema-and-unsigned-high-bit-order-v1"
CLAIMS = ("cyclic_successor", "membership")
INITIAL = (True, True, True, 0, 0, 0)


def specification(claim="cyclic_successor"):
    """Return a fresh target template; callers supply it independently at replay."""
    require(type(claim) is str and claim in CLAIMS, "supported successor claim")
    obligations = ["must subset output subset may"]
    if claim == "cyclic_successor":
        obligations += [
            "seed != may implies seed < output",
            "for every legal alternative > seed, output <= alternative",
            "seed == may implies output == must",
        ]
    return {
        "schema": SCHEMA,
        "claim": claim,
        "semantics": "unsigned mathematical payload; low w output bits only",
        "preconditions": [
            "w is a positive integer",
            "0 <= must, seed, may < 2^w",
            "must subset seed subset may",
        ],
        "legal_words": "{x in [0, 2^w): (x & must) == must and (x & ~may) == 0}",
        "obligations": obligations,
    }


def check_spec(spec):
    require(type(spec) is dict and type(spec.get("claim")) is str,
            "independently supplied successor specification")
    expected = specification(spec["claim"])
    require(digest(spec) == digest(expected), "unsupported or altered successor specification")
    return spec["claim"]


def columns():
    """All six (must, may, seed, alternative) columns, without restricting output."""
    return tuple("".join(map(str, c)) for c in product((0, 1), repeat=4)
                 if c[0] <= c[2] <= c[1] and c[0] <= c[3] <= c[1])


def order_step(previous, left, right):
    """Append a MORE significant bit: unequal high bits override the lower order.

The difference of two k-bit lower parts has absolute value below 2^k.
Therefore the new high-bit difference determines the sign when it is nonzero.
"""
    return previous if left == right else left - right


def step(state, column, output):
    legal, at_maximum, at_minimum, yg, zg, yz = state
    must, may, seed, alternative = map(int, column)
    return (
        legal and must <= output <= may,
        at_maximum and seed == may,
        at_minimum and output == must,
        order_step(yg, output, seed),
        order_step(zg, alternative, seed),
        order_step(yz, output, alternative),
    )


def violation(claim, state):
    legal, at_maximum, at_minimum, yg, zg, yz = state
    if not legal:
        return "output_outside_mask"
    if claim == "membership":
        return None
    if at_maximum:
        return None if at_minimum else "wrap_not_minimum"
    if yg <= 0:
        return "not_strictly_above_seed"
    if zg > 0 and yz > 0:
        return "skipped_legal_successor"
    return None


def decode(word, outputs):
    """Decode independently chosen input/alternative columns and emitted bits."""
    require(len(word) == len(outputs), "one output per successor column")
    values = {name: sum(int(c[j]) << i for i, c in enumerate(word))
              for j, name in enumerate(("must", "may", "seed", "alternative"))}
    return {"width": len(word), **values,
            "output": sum(int(y) << i for i, y in enumerate(outputs))}


def concrete_violation(spec, values):
    """Check a decoded witness by whole-integer masks/order, not the monitor.

The alternative is a legal quantified competitor, not another source run.
This function neither searches for a successor nor calls the order-step rules.
"""
    claim = check_spec(spec)
    require(type(values) is dict and set(values) == {
        "width", "must", "may", "seed", "alternative", "output"
    }, "concrete successor witness fields")
    width = values["width"]
    require(integer(width, 1, 4096), "concrete successor witness width")
    bound = (1 << width) - 1
    require(all(integer(values[k], 0, bound) for k in values if k != "width"),
            "concrete successor word range")
    must, may, seed, alternative, output = (
        values[k] for k in ("must", "may", "seed", "alternative", "output"))
    require(seed & must == must and seed & ~may == 0, "legal successor entry")
    require(alternative & must == must and alternative & ~may == 0,
            "legal independent successor alternative")
    if output & must != must or output & ~may:
        return "output_outside_mask"
    if claim == "membership":
        return None
    if seed == may:
        return None if output == must else "wrap_not_minimum"
    if output <= seed:
        return "not_strictly_above_seed"
    if seed < alternative < output:
        return "skipped_legal_successor"
    return None
