"""Internal PR31-equivalent witness replay on an already source-checked IR.

This helper is not a source certificate entry. Only session.load establishes
that its immutable IR snapshot corresponds to the caller's source. No parser,
carrier reconstruction, or observer search is called for a further target.
"""
from research.observations.model import require
from research.signed_predicates.semantics import evaluate
from research.signed_predicates.frontend import target_value
from research.signed_targets.common import MAX_WITNESS


def check_ir(ir, selection, monitor, proof):
    require(type(proof) is dict and set(proof) == {"kind", "word"}
            and proof["kind"] == "counterexample", "row target counterexample fields")
    word = proof["word"]
    require(type(word) is list and 0 < len(word) <= MAX_WITNESS
            and all(type(c) is str and c in monitor.alphabet for c in word),
            "bounded nonempty counterexample word")
    state = monitor.initial
    for symbol in word: state = monitor.step(state, symbol)
    require(monitor.bad(state), "counterexample must fail at its final width")
    width = len(word)
    raw = sum(int(bit) << i for i, bit in enumerate(word))
    actual = evaluate(ir, raw, width)
    expected = target_value(monitor.spec["target"], raw.bit_count(), int(word[-1]))
    require(type(actual) is bool and actual == monitor.actual(state)
            and expected == monitor.expected(state) and actual != expected,
            "whole-word source/row/target witness agreement")
    native_width = 32 if selection["word_type"] == "int" else 64
    mask = (1 << native_width) - 1
    candidates = list(dict.fromkeys((raw & mask, 0, 1, 1 << (native_width - 1),
                                    (1 << (native_width - 1)) - 1, mask)))
    native = []
    for x in candidates:
        y = evaluate(ir, x, native_width)
        require(y == monitor.runner.value(x, native_width), "native-width IR/row agreement")
        e = target_value(monitor.spec["target"], x.bit_count(), x >> (native_width - 1))
        if y != e: native.append({"input": x, "output": y, "expected": e})
    # Exact PR31 payload. None of these finite IR checks is Java execution.
    return {"status": "refuted", "word_lsb_first": word, "witness_width": width,
            "input": raw, "output": actual, "expected": expected,
            "java_width": native_width, "native_width_witnesses": native,
            "native_validation": "finite whole-word IR/row checks, not Java execution or a width-lifting theorem"}
