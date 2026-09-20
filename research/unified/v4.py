"""Unified research route: signed row targets; other profiles retain v3/v1.

Old proof envelopes replay with their original checkers. The new signed schema
never accepts source-only certificates as target certificates. No producer is
imported by check or explain. This does not change the installed qkf CLI.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys

from research.observations.model import digest, require
from research.observations.run_package import RunError
from research.wordexpr.frontend import Unsupported
from research.signed_targets.common import ENGINE, prepare
from research.signed_targets.checker import check as check_signed
from .checker import InvalidProof
from .run import load_json, save_json
from .schema import EXIT_CODES
from .v3_schema import SIGNED_KIND, compile_target

PROOF_SCHEMA = "qkf-unified-proof-v3"
RESULT_SCHEMA = "qkf-unified-result-v3"


def _result(compiled, inner):
    return {"schema": RESULT_SCHEMA, "status": inner["status"], "kind": SIGNED_KIND,
            "engine": ENGINE, "profile": "signed-terminal-row-runtime",
            "all_positive_widths": inner.get("all_positive_widths", False),
            "target_checked": inner.get("target_checked", False), "lean_checked": False,
            "inner": inner}


def check(source, target, envelope):
    require(type(source) is str, "source text")
    target, envelope = deepcopy(target), deepcopy(envelope)
    compiled = compile_target(target)
    if type(envelope) is dict and envelope.get("schema") in {
        "qkf-unified-proof-v1", "qkf-unified-proof-v2"
    }:
        from .v3 import check as check_old
        return check_old(source, target, envelope)
    try:
        require(compiled["kind"] == SIGNED_KIND, "new row envelope requires signed target")
        require(type(envelope) is dict and set(envelope) == {
            "schema", "kind", "engine", "proof", "result"
        } and envelope["schema"] == PROOF_SCHEMA and envelope["kind"] == SIGNED_KIND
                and envelope["engine"] == ENGINE, "v4 unified proof fields/engine")
        fresh = _result(compiled, check_signed(source, target, envelope["proof"]))
        require(digest(envelope["result"]) == digest(fresh), "v4 saved result differs from replay")
        return fresh
    except Exception as exc:
        raise InvalidProof(str(exc)) from exc


def prove(source, target, *, budgets=None):
    require(type(source) is str, "source text")
    target = deepcopy(target)
    compiled = compile_target(target)
    if compiled["kind"] != SIGNED_KIND:
        from .v3 import prove as prove_old
        return prove_old(source, target, budgets=budgets)
    from research.signed_targets.producer import prove as prove_signed
    certificate, inner = prove_signed(source, target, budgets=budgets)
    result = _result(compiled, inner)
    if certificate is None:
        return result, None
    envelope = {"schema": PROOF_SCHEMA, "kind": SIGNED_KIND, "engine": ENGINE,
                "proof": certificate, "result": result}
    return check(source, target, envelope), envelope


def explain(source, target, envelope):
    checked = check(source, target, envelope)
    if envelope.get("schema") != PROOF_SCHEMA:
        return {"result": checked, "route": "retained legacy checker; not row-based"}
    from research.signed_observations.explain import explain as explain_observations
    _, selection = prepare(target)
    return {"result": checked, "route": "source to observations to atomic rows to independent target",
            "interface": explain_observations(source, selection, envelope["proof"]["observations"]),
            "obligation": deepcopy(checked["inner"]["target"])}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("command", choices=("prove", "check", "explain"))
    parser.add_argument("source", type=Path)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--budget", type=Path)
    args = parser.parse_args(argv)
    try:
        require(args.command == "prove" or args.budget is None, "budgets are discovery inputs only")
        raw = args.source.read_bytes()
        require(len(raw) <= 2_000_000, "source byte budget")
        source, target = raw.decode("utf-8"), load_json(args.target)
        compile_target(target)
        if args.command == "prove":
            result, proof = prove(source, target, budgets=None if args.budget is None else load_json(args.budget))
            if proof is not None:
                save_json(args.proof, proof)
            output = result
        else:
            try:
                proof = load_json(args.proof)
            except (ValueError, RecursionError) as exc:
                raise InvalidProof(str(exc)) from exc
            output = explain(source, target, proof) if args.command == "explain" else check(source, target, proof)
            result = output["result"] if args.command == "explain" else output
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
    return EXIT_CODES.get(result["status"], 70)


if __name__ == "__main__":
    raise SystemExit(main())
