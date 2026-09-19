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


def method_tokens(source):
    return {name: _extract(source, prefix) for name, prefix in PREFIXES.items()}


def read_source(source):
    """Bind the caller and independently recognized region semantics."""
    require(type(source) is str, "create source text")
    fixture = FIXTURE.read_text(encoding="utf-8")
    actual, reference = method_tokens(source), method_tokens(fixture)
    for name in PREFIXES:
        require(actual[name] == reference[name], "changed Graal create method contract: " + name)

    descending = read_descending(source)
    ascending = read_ascending(source)
    return {
        "schema": SCHEMA,
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "fixture_sha256": hashlib.sha256(fixture.encode("utf-8")).hexdigest(),
        "methods": {name: digest(actual[name]) for name in PREFIXES},
        "descending_source_ir_sha256": digest(descending),
        "ascending_source_ir_sha256": digest(ascending),
        "rules": [
            "exact-token-bound-create-caller",
            "existing-descending-source-frontend",
            "existing-ascending-source-frontend",
        ],
    }
