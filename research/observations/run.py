"""Common research entry point: spec / verify / check / explain.

Only verify performs search. check and explain require source and specification
from the caller and independently replay both proofs. No installed qkf command
or earlier research certificate/command is changed by this module.
"""
import argparse
import json
import sys
from pathlib import Path

from .run_io import new_path, read_json, read_source, write_json, write_run
from .run_package import (EXIT_CODES, PROFILES, RESULT_SCHEMA, RunError,
                          check_package, explain_package, profile_for)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise RunError("input_error", "arguments", message)


def parser():
    root = Parser(description=__doc__, allow_abbrev=False)
    commands = root.add_subparsers(dest="command", required=True)
    target = commands.add_parser("spec", allow_abbrev=False)
    target.add_argument("output", type=Path)
    target.add_argument("--profile", choices=tuple(PROFILES), required=True)
    target.add_argument("--claim", required=True)
    for command in ("verify", "check", "explain"):
        action = commands.add_parser(command, allow_abbrev=False)
        action.add_argument("source", type=Path)
        action.add_argument("--spec", type=Path, required=True)
        action.add_argument("--profile", choices=tuple(PROFILES), required=command == "verify")
        if command == "verify":
            action.add_argument("--output", type=Path, required=True)
            action.add_argument("--budget", type=Path)
        else:
            action.add_argument("--package", type=Path, required=True)
    return root


def execute(args):
    if args.command == "spec":
        if args.profile == "ascending":
            from .successor_spec import specification
        else:
            from .upper_spec import specification
        try:
            spec = specification(args.claim)
        except (ValueError, TypeError) as exc:
            raise RunError("input_error", "specification", str(exc)) from exc
        write_json(args.output, spec)
        return {"schema": RESULT_SCHEMA, "status": "written", "profile": args.profile,
                "claim": args.claim, "meaning": "target template only; no proof"}
    source = read_source(args.source)
    spec = read_json(args.spec)
    selected = profile_for(spec, args.profile)
    if args.command == "verify":
        new_path(args.output)
        budget = read_json(args.budget) if args.budget is not None else None
        from .run_producer import verify
        result, package = verify(source, spec, profile=selected, budgets=budget)
        write_run(args.output, result, package)
        return result
    package = read_json(args.package, package=True)
    replay = explain_package if args.command == "explain" else check_package
    return replay(source, spec, package, profile=selected)


def main(argv=None):
    try:
        result = execute(parser().parse_args(argv))
    except RunError as exc:
        result = exc.result()
    except Exception as exc:
        # Unexpected faults are never accepted or mislabeled as refutations.
        # Keep stdout one machine-readable object; details remain on stderr.
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        result = {"schema": RESULT_SCHEMA, "status": "internal_error",
                  "stage": "unexpected_exception", "error": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["status"] == "written" else EXIT_CODES[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
