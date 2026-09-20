"""Bounded concrete search before any residual-carrier construction.

The ordered search is deliberately elementary: widths 1..max_width, raw words
0..2**width-1. Both ceilings bound work, not truth. Search reports are diagnostics,
never trusted proofs of absence or shortest-counterexample certificates.
"""
from copy import deepcopy
from research.wordexpr.frontend import Unsupported
from .common import SCHEMA, ENGINE, binding, budgets, point, prepare, raw_word
from .checker import check


def _certificate(compiled, ir, raw, width, actual, expected):
    return {"schema": SCHEMA, "binding": binding(compiled, ir),
            "witness": {"width": width, "raw": raw, "word": raw_word(raw, width),
                        "source_result": actual, "target_result": expected}}


def from_raw(source, target, raw, width):
    """Certify a supplied candidate word; no search or minimality assertion."""
    target = deepcopy(target)
    compiled, ir = prepare(source, target)
    actual, expected = point(compiled, ir, raw, width)
    certificate = _certificate(compiled, ir, raw, width, actual, expected)
    return certificate, check(source, target, certificate)


def probe(source, target, *, limits=None):
    """Return (certificate-or-None, checked-or-unresolved-result, diagnostics).

Only a discovered mismatch yields a certificate. Reaching the width window
without a mismatch is `not_refuted`; reaching the candidate ceiling first is
`budget_exhausted`. Neither result certifies any all-width property.
"""
    target, ceilings = deepcopy(target), budgets(limits)
    report = {"schema": "qkf-concrete-search-report-v1", "limits": ceilings,
              "order": "increasing width, then increasing raw integer", "evaluations": 0,
              "completed_widths": [], "next_candidate": None,
              "is_certificate": False, "outcome": None}

    def unresolved(status, reason):
        report["outcome"] = status
        return None, {"status": status, "engine": ENGINE, "stage": "concrete_search",
                      "reason": reason, "target_checked": False,
                      "source_interface_verified": False, "all_positive_widths": False,
                      "lean_checked": False}, report
    try:
        compiled, ir = prepare(source, target)
    except Unsupported as exc:
        result = unresolved("unsupported", str(exc))
        result[1]["stage"] = "source_profile"
        return result
    for width in range(1, ceilings["max_width"] + 1):
        for raw in range(1 << width):
            if report["evaluations"] >= ceilings["max_evaluations"]:
                report["next_candidate"] = {"width": width, "raw": raw}
                return unresolved("budget_exhausted", "concrete candidate evaluation ceiling; no proof of correctness")
            actual, expected = point(compiled, ir, raw, width)
            report["evaluations"] += 1
            if actual != expected:
                certificate = _certificate(compiled, ir, raw, width, actual, expected)
                result = check(source, target, certificate)
                report["outcome"] = "refuted"
                return certificate, result, report
        report["completed_widths"].append(width)
    return unresolved("not_refuted", "declared finite width window tested; no all-width conclusion")


def search(source, target, *, limits=None):
    """Convenience pair; use probe to retain the separate discovery diagnostics."""
    certificate, result, _ = probe(source, target, limits=limits)
    return certificate, result
