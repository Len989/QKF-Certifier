"""Unified research CLI with signed observation inference; legacy replay stays valid.

    python -m research.unified.v3 prove Demo.java --target target.json --proof proof.json
    python -m research.unified.v3 check Demo.java --target target.json --proof proof.json

No proof producer, native compiler or SMT module is imported by the replay path.
"""
import hashlib
import json
import sys

from research.observations.model import digest, require
from research.observations.run_package import RunError
from research.wordexpr.frontend import Unsupported
from research.inference.v3_adapters import CapacityExceeded
from research.inference.v3_checker import check as check_inference
from .checker import InvalidProof, check as check_legacy
from .run import load_json, parser, save_json
from .schema import EXIT_CODES, PROOF_SCHEMA as LEGACY_PROOF_SCHEMA
from .v3_schema import ENGINE, PROOF_SCHEMA, RESULT_SCHEMA, compile_target


def _binding(source, compiled):
    return {"source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "target_sha256": compiled["target_sha256"],
            "specification_sha256": compiled["specification_sha256"]}


def _result(compiled, inner):
    return {"schema": RESULT_SCHEMA, "status": inner["status"],
            "kind": compiled["kind"], "engine": ENGINE,
            "profile": compiled["profile"],
            "all_positive_widths": inner.get("all_positive_widths", False), "inner": inner}


def check(source, target, envelope):
    require(type(source) is str, "v3 source text")
    compiled = compile_target(target)
    # Existing v1 envelopes retain their original engine and checker.
    if type(envelope) is dict and envelope.get("schema") == LEGACY_PROOF_SCHEMA:
        return check_legacy(source, target, envelope)
    try:
        require(compiled["kind"] != "masked_bound", "masked bounds use the retained v1 route")
        require(type(envelope) is dict and set(envelope) == {
            "schema", "kind", "engine", "binding", "proof", "result"
        } and envelope["schema"] == PROOF_SCHEMA, "v3 unified envelope fields")
        require(envelope["kind"] == compiled["kind"] and envelope["engine"] == ENGINE,
                "v3 unified engine binding")
        require(digest(envelope["binding"]) == digest(_binding(source, compiled)),
                "v3 unified source/target/specification binding")
        fresh = _result(compiled, check_inference(source, target, envelope["proof"]))
        require(digest(envelope["result"]) == digest(fresh), "v3 saved result differs from replay")
        return fresh
    except Exception as exc:
        raise InvalidProof(str(exc)) from exc


def prove(source, target, *, budgets=None):
    compiled = compile_target(target)
    if compiled["kind"] == "masked_bound":
        from .producer import prove as legacy_prove
        return legacy_prove(source, target, budgets=budgets)
    budgets = {} if budgets is None else budgets
    require(type(budgets) is dict and set(budgets) <= {"max_features", "max_target_states"},
            "v3 inference budget fields")
    from research.inference.producer import InferenceFailure
    from research.inference.v3_producer import infer
    try:
        certificate, inner = infer(source, target, **budgets)
    except Unsupported as exc:
        return _result(compiled, {"status": "unsupported", "stage": "source_profile",
                                  "reason": str(exc)}), None
    except (InferenceFailure, CapacityExceeded) as exc:
        return _result(compiled, {"status": "budget_exhausted", "stage": "observation_inference",
                                  "reason": str(exc)}), None
    result = _result(compiled, inner)
    envelope = {"schema": PROOF_SCHEMA, "kind": compiled["kind"], "engine": ENGINE,
                "binding": _binding(source, compiled), "proof": certificate, "result": result}
    return check(source, target, envelope), envelope


def execute(args):
    raw = args.source.read_bytes()
    require(len(raw) <= 2_000_000, "source byte budget")
    source, target = raw.decode("utf-8"), load_json(args.target)
    compile_target(target)
    if args.command == "check":
        return check(source, target, load_json(args.proof))
    budgets = None if args.budget is None else load_json(args.budget)
    result, proof = prove(source, target, budgets=budgets)
    if proof is not None:
        save_json(args.proof, proof)
    return result


def main(argv=None):
    try:
        result = execute(parser().parse_args(argv))
    except InvalidProof as exc:
        result = {"schema": RESULT_SCHEMA, "status": "invalid_certificate",
                  "stage": "v3_unified_replay", "error": str(exc)}
    except RunError as exc:
        result = {"schema": RESULT_SCHEMA, "status": exc.status,
                  "stage": exc.stage, "error": str(exc)}
    except Unsupported as exc:
        result = {"schema": RESULT_SCHEMA, "status": "unsupported",
                  "stage": "source_profile", "error": str(exc)}
    except (ValueError, TypeError, KeyError, IndexError, OSError, UnicodeError, RecursionError) as exc:
        result = {"schema": RESULT_SCHEMA, "status": "input_error",
                  "stage": "v3_unified_runner", "error": str(exc)}
    except Exception as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        result = {"schema": RESULT_SCHEMA, "status": "internal_error",
                  "stage": "unexpected_exception", "error": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True))
    return EXIT_CODES.get(result["status"], 70)


if __name__ == "__main__":
    raise SystemExit(main())
