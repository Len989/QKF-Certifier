"""Replay one final-width mismatch from the caller's source and independent goal.

No search, residual transition, reduction, model, row runtime or native execution
is needed. Proof construction and concrete evaluation share retained semantics.
"""
from copy import deepcopy
from research.observations.model import digest, require
from .common import ENGINE, SCHEMA, WORD_CONVENTION, binding, point, prepare, raw_word


def check(source, target, certificate):
    target, certificate = deepcopy(target), deepcopy(certificate)
    compiled, ir = prepare(source, target)
    require(type(certificate) is dict and set(certificate) == {"schema", "binding", "witness"}
            and certificate["schema"] == SCHEMA, "concrete witness certificate fields")
    require(digest(certificate["binding"]) == digest(binding(compiled, ir)),
            "concrete source/entry/type/target/IR/contract binding")
    witness = certificate["witness"]
    require(type(witness) is dict and set(witness) == {
        "width", "raw", "word", "source_result", "target_result"
    }, "concrete witness fields")
    width, raw = witness["width"], witness["raw"]
    word = raw_word(raw, width)
    require(type(witness["word"]) is list and len(witness["word"]) == width
            and all(type(b) is str and b in {"0", "1"} for b in witness["word"])
            and witness["word"] == word, "word/raw/final-width agreement")
    actual, expected = point(compiled, ir, raw, width)
    require(type(witness["source_result"]) is bool and type(witness["target_result"]) is bool
            and witness["source_result"] == actual and witness["target_result"] == expected,
            "recomputed concrete source and goal values")
    require(actual != expected, "word does not refute the goal at its final width")
    native = 32 if compiled["specification"]["word_type"] == "int" else 64
    return {"status": "refuted", "engine": ENGINE, "claim": "concrete_source_target_mismatch",
            "target_checked": True, "source_interface_verified": False,
            "all_positive_widths": False, "refutes_all_positive_widths": True,
            "lean_checked": False, "binding": binding(compiled, ir),
            "word_convention": WORD_CONVENTION, "witness_width": width,
            "input": raw, "signed_input": raw - (1 << width) if word[-1] == "1" else raw,
            "word_lsb_first": word, "output": actual, "expected": expected,
            "native_width": native, "witness_at_native_width": width == native,
            "native_execution_checked": False, "minimum_width_checked": False,
            "scope": "one concrete word in the retained modular signed profile; no full source interface, "
                     "no width lifting to Java, no proof-assistant verification"}
