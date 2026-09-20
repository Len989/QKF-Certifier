"""Research witness-first routing. Existing positive engines are unchanged.

New concrete envelopes prove only an actual final-width counterexample. If the
bounded search finds none, prove delegates to v4, retaining its engine/schema.
Search diagnostics are separate from replayed results and never certify absence.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
from research.observations.model import digest, require
from research.observations.run_package import RunError
from research.wordexpr.frontend import Unsupported
from research.signed_witness.common import ENGINE, SIGNED_KIND, budgets as search_budgets, compile_target
from research.signed_witness.checker import check as check_concrete
from .checker import InvalidProof
from .run import load_json, save_json
from .schema import EXIT_CODES

PROOF_SCHEMA = "qkf-unified-proof-v4"
RESULT_SCHEMA = "qkf-unified-result-v4"
OLD_SCHEMAS = {"qkf-unified-proof-v1", "qkf-unified-proof-v2", "qkf-unified-proof-v3"}


def _result(inner):
    return {"schema": RESULT_SCHEMA, "status": inner["status"], "kind": SIGNED_KIND,
            "engine": ENGINE, "profile": "signed-concrete-final-width",
            "all_positive_widths": False, "target_checked": inner["target_checked"],
            "lean_checked": False, "inner": inner}


def _envelope(source, target, certificate, inner):
    result = _result(inner)
    if certificate is None:
        return result, None
    proof = {"schema": PROOF_SCHEMA, "kind": SIGNED_KIND, "engine": ENGINE,
             "proof": certificate, "result": result}
    return check(source, target, proof), proof


def check(source, target, envelope):
    require(type(source) is str, "source text")
    target, envelope = deepcopy(target), deepcopy(envelope)
    compiled = compile_target(target)
    if type(envelope) is dict and envelope.get("schema") in OLD_SCHEMAS:
        from .v4 import check as check_old
        return check_old(source, target, envelope)
    try:
        require(compiled["kind"] == SIGNED_KIND, "concrete envelope needs signed target")
        require(type(envelope) is dict and set(envelope) == {
            "schema", "kind", "engine", "proof", "result"
        } and envelope["schema"] == PROOF_SCHEMA and envelope["kind"] == SIGNED_KIND
                and envelope["engine"] == ENGINE, "v5 concrete envelope fields/engine")
        fresh = _result(check_concrete(source, target, envelope["proof"]))
        require(digest(fresh) == digest(envelope["result"]), "concrete saved result differs from replay")
        return fresh
    except Exception as exc:
        raise InvalidProof(str(exc)) from exc


def _options(compiled, value):
    value = {} if value is None else deepcopy(value)
    require(type(value) is dict and set(value) <= {"search", "fallback"}, "v5 budgets: search/fallback")
    limits = search_budgets(value.get("search"))
    fallback = value.get("fallback")
    require(fallback is None or type(fallback) is dict, "fallback budget object")
    if compiled["kind"] == SIGNED_KIND:
        from research.signed_targets.common import budgets as validate_old
        validate_old(fallback)  # Reject malformed options even if no fallback will be needed.
    else:
        require("search" not in value, "concrete search options apply only to signed targets")
    return limits, fallback


def search_with_diagnostics(source, target, *, limits=None):
    from research.signed_witness.producer import probe
    target = deepcopy(target)
    certificate, inner, report = probe(source, target, limits=limits)
    result, envelope = _envelope(source, target, certificate, inner)
    return result, envelope, report


def witness(source, target, raw, width):
    from research.signed_witness.producer import from_raw
    target = deepcopy(target)
    certificate, inner = from_raw(source, target, raw, width)
    return _envelope(source, target, certificate, inner)


def prove_with_diagnostics(source, target, *, budgets=None):
    target = deepcopy(target)
    compiled = compile_target(target)
    limits, fallback = _options(compiled, budgets)
    if compiled["kind"] == SIGNED_KIND:
        result, proof, report = search_with_diagnostics(source, target, limits=limits)
        if result["status"] in {"refuted", "unsupported"}:
            return result, proof, {"precheck": report, "fallback_used": False, "is_certificate": False}
    else:
        report = {"outcome": "not_applicable", "is_certificate": False}
    from .v4 import prove as prove_old
    result, proof = prove_old(source, target, budgets=fallback)
    # Preserve original schemas/results. The precheck is not a proof premise.
    return result, proof, {"precheck": report, "fallback_used": True, "is_certificate": False}


def prove(source, target, *, budgets=None):
    result, proof, _ = prove_with_diagnostics(source, target, budgets=budgets)
    return result, proof


def explain(source, target, envelope):
    result = check(source, target, envelope)
    if envelope["schema"] != PROOF_SCHEMA:
        from .v4 import explain as explain_old
        return explain_old(source, target, envelope)
    return {"result": result, "route": "concrete source/target evaluation; no factor construction",
            "interpretation": "word is checked at its final width, not an earlier prefix; "
                              "native-width correspondence is not actual Java execution",
            "witness": deepcopy(envelope["proof"]["witness"])}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("command", choices=("prove", "search", "witness", "check", "explain"))
    parser.add_argument("source", type=Path)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--budget", type=Path)
    parser.add_argument("--diagnostics", type=Path)
    parser.add_argument("--raw", type=int)
    parser.add_argument("--width", type=int)
    args = parser.parse_args(argv)
    try:
        require(args.command in {"prove", "search"} or (args.budget is None and args.diagnostics is None),
                "budget/diagnostics are search inputs/outputs only")
        require((args.command == "witness" and args.raw is not None and args.width is not None)
                or (args.command != "witness" and args.raw is None and args.width is None),
                "witness requires raw/width; other commands do not accept them")
        if args.command in {"prove", "search", "witness"}:
            destinations = [args.proof] + ([] if args.diagnostics is None else [args.diagnostics])
            require(len({p.resolve() for p in destinations}) == len(destinations), "distinct output paths")
            require(all(not p.exists() for p in destinations), "new output paths required")
        raw = args.source.read_bytes()
        require(len(raw) <= 2_000_000, "source byte budget")
        source, target = raw.decode("utf-8"), load_json(args.target)
        compile_target(target)
        if args.command in {"check", "explain"}:
            try:
                proof = load_json(args.proof)
            except (ValueError, RecursionError) as exc:
                raise InvalidProof(str(exc)) from exc
            output = explain(source, target, proof) if args.command == "explain" else check(source, target, proof)
            result = output["result"] if args.command == "explain" else output
        else:
            options = None if args.budget is None else load_json(args.budget)
            if args.command == "prove":
                result, proof, report = prove_with_diagnostics(source, target, budgets=options)
            elif args.command == "search":
                result, proof, report = search_with_diagnostics(source, target, limits=options)
            else:
                result, proof = witness(source, target, args.raw, args.width)
                report = None
            if proof is not None:
                save_json(args.proof, proof)
            if args.diagnostics is not None:
                save_json(args.diagnostics, report)
            output = result
    except InvalidProof as exc:
        output = result = {"schema": RESULT_SCHEMA, "status": "invalid_certificate", "error": str(exc)}
    except RunError as exc:
        output = result = {"schema": RESULT_SCHEMA, "status": exc.status, "stage": exc.stage, "error": str(exc)}
    except Unsupported as exc:
        output = result = {"schema": RESULT_SCHEMA, "status": "unsupported", "error": str(exc)}
    except (ValueError, TypeError, KeyError, IndexError, OSError, UnicodeError, RecursionError) as exc:
        output = result = {"schema": RESULT_SCHEMA, "status": "input_error", "error": str(exc)}
    except Exception as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        output = result = {"schema": RESULT_SCHEMA, "status": "internal_error", "error": type(exc).__name__}
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return {**EXIT_CODES, "not_refuted": 2}.get(result["status"], 70)


if __name__ == "__main__":
    raise SystemExit(main())
