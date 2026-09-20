"""Session-oriented research entry: verify shared source once, then independent targets.

Signed portable certificates/results stay exactly PR35/v6. Historical engines
load only when requested. This module does not import the all-profile CLI.
"""
import json
from pathlib import Path
import sys

from research.observations.model import require
from research.unified.schema import EXIT_CODES
from research.unified.v3_schema import SIGNED_KIND, compile_target
from research.unified.checker import InvalidProof
from research.wordexpr.frontend import Unsupported
from research.signed_context.io import freeze, thaw, load_json, save_json, source_text


def prove(source, target, *, budgets=None):
    source, target = source_text(source), thaw(freeze(target))
    compiled = compile_target(target)
    if compiled["kind"] != SIGNED_KIND:
        from .v3 import prove as old
        return old(source, target, budgets=budgets)
    from research.signed_context.session import build, prepare, full_budgets, wrap
    options = full_budgets(budgets)
    _, selection = prepare(target)
    context, outcome = build(source, selection, limits=options)
    if context is None: return wrap(outcome), None
    return context.prove(target, limits={k: options[k] for k in ("max_target_states", "max_witness_bits")})


def check(source, target, envelope):
    source, target = source_text(source), thaw(freeze(target))
    compile_target(target)
    # This version has no own portable proof schema. Check old dependencies cold.
    if type(envelope) is dict and envelope.get("schema") == "qkf-unified-proof-v5":
        from research.signed_context.session import check as checked
        return checked(source, target, envelope)
    from .v5 import check as old
    return old(source, target, envelope)


def explain(source, target, envelope):
    source, target = source_text(source), thaw(freeze(target))
    if type(envelope) is not dict or envelope.get("schema") != "qkf-unified-proof-v5":
        return {"result": check(source, target, envelope), "route": "retained legacy proof checker"}
    from research.signed_context.session import load, prepare, shape
    try:
        envelope = thaw(freeze(envelope))
        _, selection = prepare(target)
        proof = shape(envelope)
        return load(source, selection, proof["observations"]).explain(target, envelope)
    except Exception as exc:
        raise InvalidProof(str(exc)) from exc


def batch(source, targets, *, budgets=None, observations=None):
    """One session for 1..64 caller-supplied signed targets of the same entry.

    Returns (detached shared inspection, result/proof pairs). Missing proofs are
    unresolved diagnostics, never success certificates. Not a new compact format.
    """
    from research.signed_context.session import build, load, prepare, full_budgets, MAX_TARGETS, wrap
    source, targets = source_text(source), thaw(freeze(targets))
    require(type(targets) is list and 0 < len(targets) <= MAX_TARGETS, "1..64 batch targets")
    selections = [prepare(t)[1] for t in targets]
    require(all(freeze(s) == freeze(selections[0]) for s in selections), "one source entry/type per context")
    options = full_budgets(budgets)
    if observations is None:
        context, inspection = build(source, selections[0], limits=options)
        if context is None: return inspection, [(wrap(inspection), None) for _ in targets]
    else:
        context = load(source, selections[0], observations)
    return context.describe(), context.prove_many(targets, limits={
        k: options[k] for k in ("max_target_states", "max_witness_bits")})


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("command", choices=("prove", "check", "explain", "batch"))
    parser.add_argument("source", type=Path)
    parser.add_argument("--target", type=Path, required=True,
                        help="independent target, or array of independent targets for batch")
    parser.add_argument("--proof", type=Path, required=True,
                        help="proof file, or NEW output directory for batch")
    parser.add_argument("--budget", type=Path)
    parser.add_argument("--observations", type=Path, help="optional existing source proof for batch")
    args = parser.parse_args(argv)
    try:
        require(args.command in {"prove", "batch"} or args.budget is None, "discovery budgets only")
        require(args.command == "batch" or args.observations is None, "existing interface is a batch option")
        raw = args.source.read_bytes()
        require(len(raw) <= 2_000_000, "source byte budget")
        source, target = raw.decode("utf-8"), load_json(args.target)
        limits = load_json(args.budget) if args.budget else None
        if args.command in {"prove", "batch"}:
            require(not args.proof.exists(), "new output path required")
        if args.command == "batch":
            inspection, pairs = batch(source, target, budgets=limits,
                observations=load_json(args.observations) if args.observations else None)
            args.proof.mkdir()  # All computations/validation happen before directory creation.
            for i, (item, (result, proof)) in enumerate(zip(target, pairs)):
                save_json(args.proof / f"target-{i:03d}.json", item)
                save_json(args.proof / f"result-{i:03d}.json", result)
                if proof is not None: save_json(args.proof / f"proof-{i:03d}.json", proof)
            statuses = [result["status"] for result, _ in pairs]
            status = ("budget_exhausted" if "budget_exhausted" in statuses else
                      "unsupported" if "unsupported" in statuses else
                      "refuted" if "refuted" in statuses else "certified")
            # Batch status is only an aggregate; every target has its own proof.
            output = result = {"schema": "qkf-context-batch-report-v1", "status": status,
                "kind": "diagnostic-index-not-a-certificate", "context": inspection,
                "statuses": statuses, "proofs": sum(p is not None for _, p in pairs)}
            save_json(args.proof / "SUMMARY.json", output)
        elif args.command == "prove":
            output, proof = prove(source, target, budgets=limits)
            result = output
            if proof is not None: save_json(args.proof, proof)
        else:
            try: proof = load_json(args.proof)
            except (ValueError, RecursionError) as exc: raise InvalidProof(str(exc)) from exc
            output = explain(source, target, proof) if args.command == "explain" else check(source, target, proof)
            result = output["result"] if args.command == "explain" else output
    except InvalidProof as exc:
        output = result = {"status": "invalid_certificate", "error": str(exc)}
    except Unsupported as exc:
        output = result = {"status": "unsupported", "error": str(exc)}
    except (ValueError, TypeError, KeyError, IndexError, OSError, UnicodeError, RecursionError) as exc:
        output = result = {"status": "input_error", "error": str(exc)}
    except Exception as exc:
        # Preserve a delegated legacy structured failure without eager all-profile imports.
        if type(exc).__name__ == "RunError" and type(exc).__module__ == "research.observations.run_package":
            output = result = {"status": exc.status, "stage": exc.stage, "error": str(exc)}
        else:
            print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
            output = result = {"status": "internal_error", "error": type(exc).__name__}
    print(json.dumps(output, sort_keys=True, allow_nan=False))
    return EXIT_CODES.get(result["status"], 70)


if __name__ == "__main__": raise SystemExit(main())
