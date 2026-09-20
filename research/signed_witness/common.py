"""Contracts for concrete refutation; no residual model or observation dependency.

The target and word semantics are retained, not inferred from the source name.
A point check says nothing about untested inputs or existence of a finite factor.
"""
from research.observations.model import digest, integer, require
from research.signed_predicates.frontend import CONTRACT, read_source, target_value
from research.signed_predicates import semantics
from research.unified.v3_schema import SIGNED_KIND, compile_target

SCHEMA = "qkf-signed-concrete-witness-v1"
ENGINE = "signed-concrete-witness-v1"
MAX_WIDTH = 4096
MAX_ENUM_WIDTH = 20
MAX_EVALUATIONS = 1_000_000
DEFAULTS = {"max_width": 8, "max_evaluations": 510}
WORD_CONVENTION = "nonempty-lsb-first-final-width-v1"


def prepare(source, target):
    require(type(source) is str, "source text")
    compiled = compile_target(target)
    require(compiled["kind"] == SIGNED_KIND, "concrete witness requires signed_boolean_predicate")
    spec = compiled["specification"]
    ir = read_source(source, spec["entry"], spec["word_type"])
    return compiled, ir


def binding(compiled, ir):
    return {"source_sha256": ir["source_sha256"],
            "declaration_sha256": ir["declaration_sha256"],
            "source_ir_sha256": digest(ir),
            "target_sha256": compiled["target_sha256"],
            "specification_sha256": compiled["specification_sha256"],
            "contract": CONTRACT, "word_convention": WORD_CONVENTION}


def raw_word(raw, width):
    require(integer(width, 1, MAX_WIDTH), "concrete width must be 1..4096")
    require(integer(raw, 0, (1 << width) - 1), "raw word must fit its width; no coercion")
    return [str((raw >> i) & 1) for i in range(width)]


def point(compiled, ir, raw, width):
    raw_word(raw, width)
    actual = semantics.evaluate(ir, raw, width)
    expected = target_value(compiled["specification"]["target"], raw.bit_count(), raw >> (width - 1))
    require(type(actual) is bool and type(expected) is bool, "Boolean source and independent target")
    return actual, expected


def budgets(value=None):
    value = {} if value is None else value
    require(type(value) is dict and set(value) <= set(DEFAULTS), "concrete search budget fields")
    result = {**DEFAULTS, **value}
    require(integer(result["max_width"], 0, MAX_ENUM_WIDTH), "search width ceiling 0..20")
    require(integer(result["max_evaluations"], 0, MAX_EVALUATIONS), "search evaluation ceiling 0..1000000")
    return result
