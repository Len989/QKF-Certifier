"""Executable mathematical model and independent denotation decision procedure.

The create model follows the accepted source operations. Validation does not use
this implementation as its oracle: exact denotation extrema/equivalence are
decided separately by a small digit-DP over signed-order bit patterns.
"""
from functools import lru_cache

from .model import integer, require

SUPPORTED_BITS = (1, 8, 16, 32, 64)
U64 = (1 << 64) - 1


def word_mask(bits):
    return (1 << bits) - 1


def signed_word(value, bits):
    value &= word_mask(bits)
    sign = 1 << (bits - 1)
    return value - (1 << bits) if value & sign else value


def java_long(value):
    value &= U64
    return value - (1 << 64) if value & (1 << 63) else value


def unsigned_word(value, bits):
    return value & word_mask(bits)


def min_value(bits):
    return -(1 << (bits - 1))


def max_value(bits):
    return (1 << (bits - 1)) - 1


def significant_bit(bits, value):
    return (unsigned_word(value, bits) >> (bits - 1)) & 1


def min_value_for_masks(bits, must, may):
    if significant_bit(bits, may) == 0:
        return signed_word(must, bits)
    return signed_word(must | (1 << (bits - 1)), bits)


def max_value_for_masks(bits, must, may):
    if significant_bit(bits, must) == 1:
        return signed_word(may, bits)
    return may & (word_mask(bits) >> 1)


def set_optional_bits(bits, bound, must, may, initial):
    optional = may & ~must & word_mask(bits - 1) if bits > 1 else 0
    value = initial
    for position in range(bits - 1, -1, -1):
        bit = 1 << position
        if bit & optional:
            candidate = signed_word(unsigned_word(value, bits) | bit, bits)
            if candidate <= bound:
                value = candidate
    return value


def compute_upper_bound(bits, upper, must, may, can_zero):
    value = signed_word(must, bits)
    if upper < 0 or value > upper:
        value = min_value_for_masks(bits, must, may)
    value = set_optional_bits(bits, upper, must, may, value)

    if value == 0 and not can_zero:
        if significant_bit(bits, may) == 0:
            return min_value(bits)
        value = max_value_for_masks(bits, must | (1 << (bits - 1)), may)

    return min_value(bits) if value > upper else value


def _trailing_zeros_64(value):
    value &= U64
    if value == 0:
        return 64
    return (value & -value).bit_length() - 1


def compute_lower_bound(bits, lower, must, may, can_zero):
    value = min_value_for_masks(bits, must, may)
    optional = may & ~must & (word_mask(bits - 1) if bits > 1 else 0)

    if value < lower:
        if optional == 0:
            value = 0
        else:
            for position in range(bits - 1, -1, -1):
                bit = 1 << position
                if bit & optional:
                    candidate = signed_word(unsigned_word(value, bits) + bit, bits)
                    if candidate <= lower:
                        value = candidate

            if value < lower:
                incremented = False
                for position in range(0, bits - 1):
                    bit = 1 << position
                    if incremented:
                        raw = unsigned_word(value, bits)
                        if bit & must and not raw & bit:
                            value = signed_word(raw | bit, bits)
                            raw = unsigned_word(value, bits)
                        if not bit & may and raw & bit:
                            value = signed_word(raw + bit, bits)
                    elif bit & optional:
                        value = signed_word(unsigned_word(value, bits) + bit, bits)
                        incremented = True

    if value == 0 and not can_zero:
        signed_must = java_long(must)
        if signed_must > 0:
            value = signed_word(must, bits)
        elif signed_must == 0:
            low_bit = _trailing_zeros_64(may)
            value = signed_word(1 << (low_bit & 63), bits)
        else:
            value = max_value(bits)

    return max_value(bits) if value < lower else value


def source_empty(lower, upper, must, may):
    return lower > upper or bool(must & ~may) or (may == 0 and (lower > 0 or upper < 0))


def _common_prefix_masks(bits, lower, upper):
    if lower == upper:
        raw = unsigned_word(lower, bits)
        return raw, raw
    xor64 = (lower & U64) ^ (upper & U64)
    same = 64 - xor64.bit_length()
    suffix = 0 if same == 64 else (1 << (64 - same)) - 1
    bounded_may = (lower & U64) | suffix
    bounded_must = (lower & U64) & (~suffix & U64)
    m = word_mask(bits)
    return bounded_must & m, bounded_may & m


def interval_masks(bits, lower, upper):
    """Masks used by the exact three-argument range constructor."""
    return _common_prefix_masks(bits, lower, upper)


def contains_zero(lower, upper, must, may, can_zero):
    return (
        can_zero
        and lower <= 0 <= upper
        and must == 0
        and 0 & ~may == 0
    )


def normalize_input(values):
    require(type(values) is dict and set(values) == {
        "bits", "lower", "upper", "must", "may", "can_zero"
    }, "create input fields")
    bits = values["bits"]
    require(bits in SUPPORTED_BITS, "supported Graal bit width")
    lo, hi = min_value(bits), max_value(bits)
    require(integer(values["lower"], lo, hi) and integer(values["upper"], lo, hi),
            "signed create bounds")
    limit = word_mask(bits)
    require(integer(values["must"], 0, limit) and integer(values["may"], 0, limit),
            "create mask range")
    require(type(values["can_zero"]) is bool, "Boolean can_zero")
    return dict(values)


def _result(bits, lower, upper, must, may, can_zero, iterations, path):
    return {
        "kind": "value",
        "lower": lower,
        "upper": upper,
        "must": must,
        "may": may,
        "zero_member": contains_zero(lower, upper, must, may, can_zero),
        "iterations": iterations,
        "path": path,
    }


def execute_create(values):
    """Execute the mathematical transcription of the exact source normalization."""
    v = normalize_input(values)
    bits, lower, upper = v["bits"], v["lower"], v["upper"]
    must, may, can_zero = v["must"], v["may"], v["can_zero"]
    default = word_mask(bits)

    if source_empty(lower, upper, must, may):
        return {"kind": "empty", "iterations": 0, "path": "early_empty"}

    if must == 0 and may == default and can_zero:
        bounded_must, bounded_may = interval_masks(bits, lower, upper)
        return _result(bits, lower, upper, bounded_must, bounded_may, True, 0,
                       "unrestricted_delegate")

    current = (lower, upper, must, may)
    for iteration in range(1, 4):
        lower_current, upper_current, must_current, may_current = current

        lower_tmp = max(lower_current, min_value_for_masks(bits, must_current, may_current))
        upper_tmp = min(upper_current, max_value_for_masks(bits, must_current, may_current))

        bounded_must, bounded_may = _common_prefix_masks(bits, lower_tmp, upper_tmp)
        must_tmp = default & (must_current | bounded_must)
        may_tmp = default & may_current & bounded_may

        upper_tmp = min(upper_tmp, max_value_for_masks(bits, must_tmp, may_tmp))
        lower_tmp = max(lower_tmp, min_value_for_masks(bits, must_tmp, may_tmp))

        upper_tmp = compute_upper_bound(bits, upper_tmp, must_tmp, may_tmp, can_zero)
        lower_tmp = compute_lower_bound(bits, lower_tmp, must_tmp, may_tmp, can_zero)

        following = (lower_tmp, upper_tmp, must_tmp, may_tmp)
        if source_empty(*following):
            return {"kind": "empty", "iterations": iteration, "path": "loop_empty"}

        if following == current:
            return _result(bits, *following, can_zero, iteration, "stable")

        require(lower_tmp >= lower_current, "model lower monotonicity")
        require(upper_tmp <= upper_current, "model upper monotonicity")
        current = following

    raise ValueError("source iteration limit would be exceeded")


def _bias(bits, signed):
    return unsigned_word(signed, bits) ^ (1 << (bits - 1))


def _signed_from_bias(bits, biased):
    return signed_word(biased ^ (1 << (bits - 1)), bits)


def _extreme(values, *, smallest=True, extra_must=0, extra_may=None,
             lower=None, upper=None, allow_zero=None):
    """Independent digit-DP extremum for interval plus per-bit requirements."""
    v = normalize_input(values)
    bits = v["bits"]
    lo = v["lower"] if lower is None else max(v["lower"], lower)
    hi = v["upper"] if upper is None else min(v["upper"], upper)
    if lo > hi:
        return None

    must = v["must"] | extra_must
    may = v["may"] if extra_may is None else v["may"] & extra_may
    if must & ~may:
        return None
    can_zero = v["can_zero"] if allow_zero is None else allow_zero

    low_key, high_key = _bias(bits, lo), _bias(bits, hi)
    sign = 1 << (bits - 1)

    @lru_cache(maxsize=None)
    def feasible(position, tight_low, tight_high, nonzero):
        if position < 0:
            return can_zero or nonzero
        low_bit = (low_key >> position) & 1 if tight_low else 0
        high_bit = (high_key >> position) & 1 if tight_high else 1
        order = (0, 1) if smallest else (1, 0)
        for ybit in order:
            if not low_bit <= ybit <= high_bit:
                continue
            ubit = ybit ^ (1 if (1 << position) == sign else 0)
            if must & (1 << position) and not ubit:
                continue
            if not may & (1 << position) and ubit:
                continue
            if feasible(
                position - 1,
                tight_low and ybit == low_bit,
                tight_high and ybit == high_bit,
                nonzero or bool(ubit),
            ):
                return True
        return False

    if not feasible(bits - 1, True, True, False):
        return None

    key = 0
    tight_low = tight_high = True
    nonzero = False
    for position in range(bits - 1, -1, -1):
        low_bit = (low_key >> position) & 1 if tight_low else 0
        high_bit = (high_key >> position) & 1 if tight_high else 1
        order = (0, 1) if smallest else (1, 0)
        for ybit in order:
            if not low_bit <= ybit <= high_bit:
                continue
            ubit = ybit ^ (1 if position == bits - 1 else 0)
            if must & (1 << position) and not ubit:
                continue
            if not may & (1 << position) and ubit:
                continue
            if feasible(
                position - 1,
                tight_low and ybit == low_bit,
                tight_high and ybit == high_bit,
                nonzero or bool(ubit),
            ):
                key |= ybit << position
                tight_low = tight_low and ybit == low_bit
                tight_high = tight_high and ybit == high_bit
                nonzero = nonzero or bool(ubit)
                break
        else:
            raise AssertionError("digit-DP reconstruction")
    return _signed_from_bias(bits, key)


def exact_extrema(values):
    return _extreme(values, smallest=True), _extreme(values, smallest=False)


def _has(values, **kwargs):
    return _extreme(values, smallest=True, **kwargs) is not None


def subset(left, right):
    """Decide exact inclusion of two interval/mask/zero denotations."""
    a, b = normalize_input(left), normalize_input(right)
    require(a["bits"] == b["bits"], "same bit width for denotation inclusion")
    bits = a["bits"]

    if _extreme(a, smallest=True) is None:
        return True
    if _extreme(b, smallest=True) is None:
        return False

    if _has(a, upper=b["lower"] - 1):
        return False
    if _has(a, lower=b["upper"] + 1):
        return False

    for position in range(bits):
        bit = 1 << position
        if b["must"] & bit:
            if _has(a, extra_may=word_mask(bits) ^ bit):
                return False
        if not b["may"] & bit:
            if _has(a, extra_must=bit):
                return False

    if not b["can_zero"] and a["can_zero"]:
        if a["lower"] <= 0 <= a["upper"] and a["must"] == 0:
            return False
    return True


def result_constraints(original, result):
    if result["kind"] == "empty":
        return None
    return {
        "bits": original["bits"],
        "lower": result["lower"],
        "upper": result["upper"],
        "must": result["must"],
        "may": result["may"],
        "can_zero": result["zero_member"],
    }


def equivalent_result(values, result):
    original = normalize_input(values)
    lo, hi = exact_extrema(original)
    if lo is None:
        return result["kind"] == "empty"
    if result["kind"] != "value" or result["lower"] != lo or result["upper"] != hi:
        return False
    normalized = result_constraints(original, result)
    return subset(original, normalized) and subset(normalized, original)
