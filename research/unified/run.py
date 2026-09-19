"""One research CLI for all currently supported QKF target profiles."""

import argparse
import json
import sys
from pathlib import Path

from research.observations.run_package import RunError
from research.wordexpr.frontend import Unsupported

from .checker import InvalidProof, check
from .schema import EXIT_CODES, RESULT_SCHEMA, compile_target


def load_json(path):
    raw = Path(path).read_bytes()
    if len(raw) > 5_000_000:
        raise ValueError("JSON byte budget")

    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate JSON key: " + key)
            out[key] = value
        return out

    def nonfinite(value):
        raise ValueError("nonfinite JSON number: " + value)

    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite)


def save_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def parser():
    root = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = root.add_subparsers(dest="command", required=True)
    for action in ("prove", "check"):
        p = commands.add_parser(action, allow_abbrev=False)
        p.add_argument("source", type=Path)
        p.add_argument("--target", type=Path, required=True)
        p.add_argument("--proof", type=Path, required=True)
        if action == "prove":
            p.add_argument("--budget", type=Path)
    return root


def execute(args):
    raw = args.source.read_bytes()
    if len(raw) > 2_000_000:
        raise ValueError("source byte budget")
    source = raw.decode("utf-8")
    target = load_json(args.target)
    compile_target(target)

    if args.command == "check":
        return check(source, target, load_json(args.proof))

    from .producer import prove

    budgets = load_json(args.budget) if args.budget is not None else None
    result, envelope = prove(source, target, budgets=budgets)
    if envelope is not None:
        save_json(args.proof, envelope)
    return result


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        result = execute(args)
    except InvalidProof as exc:
        result = {
            "schema": RESULT_SCHEMA,
            "status": "invalid_certificate",
            "stage": "unified_replay",
            "error": str(exc),
        }
    except RunError as exc:
        result = {
            "schema": RESULT_SCHEMA,
            "status": exc.status,
            "stage": exc.stage,
            "error": str(exc),
        }
    except Unsupported as exc:
        result = {
            "schema": RESULT_SCHEMA,
            "status": "unsupported",
            "stage": "source_profile",
            "error": str(exc),
        }
    except (ValueError, TypeError, KeyError, IndexError, OSError, UnicodeError, RecursionError) as exc:
        result = {
            "schema": RESULT_SCHEMA,
            "status": "input_error",
            "stage": "unified_runner",
            "error": str(exc),
        }
    except Exception as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        result = {
            "schema": RESULT_SCHEMA,
            "status": "internal_error",
            "stage": "unexpected_exception",
            "error": type(exc).__name__,
        }
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True))
    return EXIT_CODES.get(result["status"], 70)


if __name__ == "__main__":
    raise SystemExit(main())
