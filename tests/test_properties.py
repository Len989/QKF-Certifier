from hypothesis import given, settings
from hypothesis import strategies as st
from word_oracle import expr_value

from qkf_certifier.producer import normalize

leaves = st.sampled_from(
    [("var", i) for i in range(4)] + [("zero",), ("ones",), ("const", 1), ("const", 2), ("width",)]
)
unary = st.sampled_from(
    [
        "not",
        "countl_one",
        "countl_zero",
        "countr_one",
        "countr_zero",
        "clear_sign_bit",
        "set_sign_bit",
    ]
)
binary = st.sampled_from(
    [
        "and",
        "or",
        "xor",
        "add",
        "sub",
        "mul",
        "shl",
        "lshr",
        "ashr",
        "umin",
        "umax",
        "smin",
        "smax",
        "clear_low_bits",
        "clear_high_bits",
        "set_low_bits",
        "set_high_bits",
        "udiv",
        "urem",
        "sdiv",
        "srem",
    ]
)
expressions = st.recursive(
    leaves,
    lambda child: st.one_of(st.tuples(unary, child), st.tuples(binary, child, child)),
    max_leaves=20,
)


@settings(max_examples=500, deadline=None, derandomize=True)
@given(expressions, st.integers(1, 16), st.lists(st.integers(0, 65535), min_size=4, max_size=4))
def test_random_typed_normalizations_preserve_word_semantics(e, width, values):
    mask = (1 << width) - 1
    za, oa, zb, ob = [x & mask for x in values]
    oa &= mask ^ za
    ob &= mask ^ zb
    nf, _ = normalize(e)
    assert expr_value(e, (za, oa, zb, ob), width) == expr_value(nf, (za, oa, zb, ob), width)
