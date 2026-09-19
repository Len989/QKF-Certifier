"""Independent contract for the source-bound Graal create normalization slice."""

from .model import digest, require

SCHEMA = "qkf-graal-create-normalization-spec-v1"


def specification():
    return {
        "schema": SCHEMA,
        "claim": "integer_stamp_create_normalization",
        "input": {
            "bits": [1, 8, 16, 32, 64],
            "bounds": "signed values representable by bits",
            "masks": "unsigned bit patterns contained in the low bits",
            "can_be_zero": "Boolean zero-admissibility flag",
        },
        "denotation": (
            "{x: lower<=x<=upper, required mask bits are set, forbidden mask bits are clear, "
            "and (canBeZero or x!=0)}"
        ),
        "obligations": [
            "Empty is returned only and exactly when the input denotation is empty",
            "a nonempty return has exactly the same denotation as the input",
            "returned lower and upper bounds are the exact signed extrema of that denotation",
            "every reusable helper premise is derived from the caller state before use",
            "the loop monotonicity guarantees hold",
            "the normalization loop reaches a fixed point within the three source iterations",
        ],
        "scope": "the exact pinned caller shape and supported Graal bit widths; not arbitrary Java",
    }


def check_spec(spec):
    require(type(spec) is dict and digest(spec) == digest(specification()),
            "independent exact Graal create normalization specification")
