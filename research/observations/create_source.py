"""Exact source binding for the Graal IntegerStamp.create normalization caller.

The accepted source language here is deliberately one pinned caller shape, not a
general Java frontend. Relevant method token streams must equal the retained
compiled fixture; the two reusable helper regions are additionally reparsed by
their existing independent source frontends.
"""
import hashlib
from pathlib import Path

from .ascending_source import read_source as read_ascending
from .java_words import read_source as read_descending, tokens
from .model import digest, require

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "research/graal/native/IntegerStamp.java"
SCHEMA = "qkf-graal-create-source-v1"

PREFIXES = {
    "create_full": "public static IntegerStamp create ( int bits , long lowerBoundInput , long upperBoundInput , long mustBeSetInput , long mayBeSetInput , boolean canBeZero ) {",
    "create_range": "public static IntegerStamp create ( int bits , long lowerBoundInput , long upperBoundInput ) {",
    "create_constant": "public static IntegerStamp createConstant ( int bits , long value ) {",
    "ctor_empty": "private IntegerStamp ( int bits , boolean empty ) {",
    "ctor_constant": "private IntegerStamp ( int bits , long constant ) {",
    "ctor_range": "private IntegerStamp ( int bits , long lowerBound , long upperBound ) {",
    "ctor_full": "private IntegerStamp ( int bits , long lowerBound , long upperBound , long mustBeSet , long mayBeSet , boolean canBeZero ) {",
    "contains": "private boolean contains ( long value , boolean isCanBeZero ) {",
    "is_empty": "private static boolean isEmpty ( long lowerBound , long upperBound , long mustBeSet , long mayBeSet ) {",
    "min_masks": "private static long minValueForMasks ( int bits , long mustBeSet , long mayBeSet ) {",
    "max_masks": "private static long maxValueForMasks ( int bits , long mustBeSet , long mayBeSet ) {",
    "upper": "private static long computeUpperBound ( int bits , long upperBound , long mustBeSet , long mayBeSet , boolean canBeZero ) {",
    "optional": "private static long setOptionalBits ( int bits , long bound , long mustBeSet , long mayBeSet , long initialValue ) {",
    "lower": "private static long computeLowerBound ( int bits , long lowerBound , long mustBeSet , long mayBeSet , boolean canBeZero ) {",
}


def _words(text):
    return [m.group() for m in tokens(text)]


def _extract(source, prefix):
    words = _words(source)
    wanted = prefix.split()
    starts = [i for i in range(len(words)) if words[i:i + len(wanted)] == wanted]
    require(len(starts) == 1, "one exact Graal method: " + prefix.split("(")[0].strip())
    start = starts[0]
    brace = start + len(wanted) - 1
    require(words[brace] == "{", "method opening brace")
    depth = 0
    for end in range(brace, len(words)):
        depth += (words[end] == "{") - (words[end] == "}")
        if depth == 0:
            return words[start:end + 1]
    raise ValueError("unclosed Graal method")


PRIMITIVE_FORMS = {
    "minValue": (
        "static long minValue(int bits){return bits==64 ? Long.MIN_VALUE : -(1L<<(bits-1));}",
        "public static long minValue(int bits){assert 0 < bits && bits <= 64; return -1L << (bits - 1);}",
    ),
    "maxValue": (
        "static long maxValue(int bits){return bits==64 ? Long.MAX_VALUE : (1L<<(bits-1))-1;}",
        "public static long maxValue(int bits){assert 0 < bits && bits <= 64; return mask(bits - 1);}",
    ),
    "signExtend": (
        "static long signExtend(long v,int bits){return bits==64 ? v : (v<<(64-bits))>>(64-bits);}",
        "public static long signExtend(long value, int inputBits){"
        "if (inputBits < 64){if ((value >>> (inputBits - 1) & 1) == 1){"
        "return value | (-1L << inputBits);} else {return value & ~(-1L << inputBits);}}"
        "else {return value;}}",
    ),
}



EMPTY_FACTORY_FORMS = (
    "static IntegerStamp createEmptyStamp(int bits){return new IntegerStamp(bits,true);}",
    "static IntegerStamp createEmptyStamp(int bits){assert isPowerOf2(bits); "
    "return emptyStamps[CodeUtil.log2(bits)];}",
)
EMPTY_CACHE_FORM = (
    "static final IntegerStamp[] emptyStamps = new IntegerStamp[CodeUtil.log2(64) + 1]; "
    "static final IntegerStamp[] unrestrictedStamps = new IntegerStamp[CodeUtil.log2(64) + 1]; "
    "static {for (int logBits = 0; logBits < emptyStamps.length; logBits++) {"
    "emptyStamps[logBits] = new IntegerStamp(1 << logBits, true); "
    "unrestrictedStamps[logBits] = new IntegerStamp(1 << logBits, false);}}"
)


def _contains_sequence(words, form):
    wanted = _words(form)
    return sum(words[i:i + len(wanted)] == wanted
               for i in range(len(words) - len(wanted) + 1))


def _empty_factory(source):
    words = _words(source)
    forms = [_words(x) for x in EMPTY_FACTORY_FORMS]
    matches = [form for form in forms
               if any(words[i:i + len(form)] == form
                      for i in range(len(words) - len(form) + 1))]
    require(len(matches) == 1, "one accepted createEmptyStamp implementation")
    cached = matches[0] == forms[1]
    if cached:
        require(_contains_sequence(words, EMPTY_CACHE_FORM) == 1,
                "exact cached empty/unrestricted stamp initialization")
    return {"kind": "cached" if cached else "direct",
            "sha256": digest(matches[0]),
            "cache_sha256": digest(_words(EMPTY_CACHE_FORM)) if cached else None}


def method_tokens(source):
    return {name: _extract(source, prefix) for name, prefix in PREFIXES.items()}


def _primitive(source, name):
    words = _words(source)
    accepted = [_words(form) for form in PRIMITIVE_FORMS[name]]
    matches = []
    for form in accepted:
        for i in range(len(words) - len(form) + 1):
            if words[i:i + len(form)] == form:
                matches.append(form)
    require(len(matches) == 1, "one accepted CodeUtil." + name + " implementation")
    return matches[0]


def read_source(source):
    """Bind the caller and independently recognized region semantics."""
    require(type(source) is str, "create source text")
    fixture = FIXTURE.read_text(encoding="utf-8")
    actual, reference = method_tokens(source), method_tokens(fixture)
    for name in PREFIXES:
        require(actual[name] == reference[name], "changed Graal create method contract: " + name)

    words = _words(source)
    require(sum(words[i:i + 6] == ["static", "final", "int", "ITERATION_LIMIT", "=", "3"]
                for i in range(len(words) - 5)) == 1,
            "exact three-pass source iteration limit")

    primitives = {name: _primitive(source, name) for name in PRIMITIVE_FORMS}
    empty_factory = _empty_factory(source)
    descending = read_descending(source)
    ascending = read_ascending(source)
    return {
        "schema": SCHEMA,
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "fixture_sha256": hashlib.sha256(fixture.encode("utf-8")).hexdigest(),
        "methods": {name: digest(actual[name]) for name in PREFIXES},
        "primitives": {name: digest(value) for name, value in primitives.items()},
        "empty_factory": empty_factory,
        "descending_source_ir_sha256": digest(descending),
        "ascending_source_ir_sha256": digest(ascending),
        "rules": [
            "exact-token-bound-create-caller",
            "existing-descending-source-frontend",
            "existing-ascending-source-frontend",
            "exact-iteration-limit",
            "accepted-CodeUtil-signed-extrema-and-extension",
            "accepted-direct-or-cached-empty-factory",
        ],
    }
