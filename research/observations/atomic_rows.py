"""Check and evaluate the finite-union normal form of a forced preimage row.

The caller checks supplied cells against native labels first. Pairwise-disjoint
atom images force all intersections; finite unions force every other cell.
The kernel is equality after projection to atoms with nonempty images.
No powerset enumeration, producer import or certificate code execution is used.
"""
from .model import integer, require


def check_completion(row, classes):
    values = dict(row["supplied"])
    atoms = [values[1 << j] for j in range(classes)]
    require(all(atoms[i] & atoms[j] == 0 for i in range(classes) for j in range(i)),
            "atomic row images must be disjoint")
    require(row["extension"] == "finite-unions", "atomic row extension rule")
    empty = row["empty"]
    if classes == 1:
        require(empty == {"kind": "native"} and values.get(0) == 0, "native empty cell")
    else:
        require(type(empty) is dict and set(empty) == {"kind", "left", "right"}
                and empty["kind"] == "intersection" and type(empty["left"]) is int
                and type(empty["right"]) is int and empty["left"] == 1 and empty["right"] == 2,
                "empty cell forced by distinct atoms")
    visible = sum(1 << j for j, image in enumerate(atoms) if image)
    require(integer(row["kernel_projection"], 0, (1 << classes) - 1)
            and row["kernel_projection"] == visible, "atomic row kernel projection")


def image(row, subset, classes):
    """Evaluate a row normal form after its containing certificate was checked."""
    require(integer(subset, 0, (1 << classes) - 1), "atomic row argument")
    result = 0
    for atom, value in row["supplied"]:
        if subset & atom:
            result |= value
    return result
