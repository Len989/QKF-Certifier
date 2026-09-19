"""Proof-producing side of the unified research runner."""

import hashlib

from research.observations.model import digest

from .checker import check, normalize
from .schema import PROOF_SCHEMA, RESULT_SCHEMA, compile_target


def _plain(compiled, status, stage, reason):
    inner = {"status": status, "stage": stage, "reason": str(reason)}
    return normalize(compiled, inner), None


def _word_proof(source, compiled):
    kind, spec = compiled["kind"], compiled["specification"]
    if kind == "word_result":
        from research.wordexpr.producer import Budget, derive
    else:
        from research.wordexpr.predicate_producer import derive
        from research.wordexpr.producer import Budget
    from research.wordexpr.frontend import Unsupported

    try:
        return derive(source, spec)
    except Budget as exc:
        return _plain(compiled, "budget_exhausted", "word_search", exc)
    except Unsupported as exc:
        return _plain(compiled, "unsupported", "source_profile", exc)


def prove(source, target, *, budgets=None):
    """Search using the selected existing engine, then independently replay it."""
    compiled = compile_target(target)
    kind, spec = compiled["kind"], compiled["specification"]

    if kind in {"word_result", "boolean_predicate"}:
        proposed = _word_proof(source, compiled)
        if proposed[1] is None and proposed[0].get("schema") == RESULT_SCHEMA:
            return proposed
        proof, inner = proposed
    else:
        from research.observations.run_producer import verify

        inner, proof = verify(source, spec, profile=compiled["profile"], budgets=budgets)
        if proof is None:
            return normalize(compiled, inner), None

    result = normalize(compiled, inner)
    envelope = {
        "schema": PROOF_SCHEMA,
        "kind": kind,
        "engine": compiled["engine"],
        "binding": {
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "target_sha256": compiled["target_sha256"],
            "specification_sha256": compiled["specification_sha256"],
        },
        "proof": proof,
        "result": result,
    }
    fresh = check(source, target, envelope)
    if digest(fresh) != digest(result):
        raise ValueError("unified producer/replay mismatch")
    return fresh, envelope
