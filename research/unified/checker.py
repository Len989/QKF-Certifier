"""Independent replay for qkf-unified-proof-v1; never imports proof producers."""

import hashlib

from research.observations.model import digest, require

from .schema import PROOF_SCHEMA, RESULT_SCHEMA, compile_target


class InvalidProof(ValueError):
    pass


def normalize(compiled, result):
    require(type(result) is dict and type(result.get("status")) is str, "inner result")
    return {
        "schema": RESULT_SCHEMA,
        "status": result["status"],
        "kind": compiled["kind"],
        "engine": compiled["engine"],
        "profile": compiled["profile"],
        "all_positive_widths": bool(
            result.get(
                "all_positive_widths",
                result.get("scope", {}).get("all_positive_payload_widths", False),
            )
        ),
        "inner": result,
    }


def _inner_check(source, compiled, proof):
    kind, spec = compiled["kind"], compiled["specification"]
    if kind == "word_result":
        from research.wordexpr.checker import check

        return check(source, spec, proof)
    if kind == "boolean_predicate":
        from research.wordexpr.predicate_checker import check

        return check(source, spec, proof)

    from research.observations.run_package import check_package

    return check_package(source, spec, proof, profile=compiled["profile"])


def check(source, target, envelope):
    """Replay the selected proof against caller-supplied source and target."""
    require(type(source) is str, "source text")
    compiled = compile_target(target)
    try:
        require(
            type(envelope) is dict
            and set(envelope) == {
                "schema",
                "kind",
                "engine",
                "binding",
                "proof",
                "result",
            }
            and envelope["schema"] == PROOF_SCHEMA,
            "unified proof fields",
        )
        require(
            envelope["kind"] == compiled["kind"] and envelope["engine"] == compiled["engine"],
            "unified proof engine binding",
        )
        expected_binding = {
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "target_sha256": compiled["target_sha256"],
            "specification_sha256": compiled["specification_sha256"],
        }
        require(digest(envelope["binding"]) == digest(expected_binding), "source and target binding")
        fresh = normalize(compiled, _inner_check(source, compiled, envelope["proof"]))
        require(digest(envelope["result"]) == digest(fresh), "saved unified result differs from replay")
        return fresh
    except InvalidProof:
        raise
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise InvalidProof(str(exc)) from exc
