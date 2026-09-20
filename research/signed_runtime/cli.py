"""Check once, inspect or execute a signed source-observation proof via rows."""
import argparse
import json
from pathlib import Path

from research.signed_bridge.cli import load as load_json
from research.signed_bridge.model import request
from research.wordexpr.frontend import Unsupported
from .runtime import ExecutionLimit, load


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "run"))
    parser.add_argument("source", type=Path)
    parser.add_argument("--class", dest="class_name", required=True)
    parser.add_argument("--method", required=True)
    parser.add_argument("--word-type", choices=("int", "long"), required=True)
    parser.add_argument("--certificate", type=Path, required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--bits", help="LSB-first binary string; an empty string is not a word")
    group.add_argument("--raw", type=int, help="nonnegative raw word in decimal")
    parser.add_argument("--width", type=int)
    args = parser.parse_args(argv)
    stage = "input"
    try:
        if args.command == "inspect" and (args.bits is not None or args.raw is not None or args.width is not None):
            raise ValueError("inspect does not take an execution input")
        if args.command == "run":
            if args.bits is None and args.raw is None:
                raise ValueError("run requires --bits or --raw with --width")
            if (args.raw is not None) != (args.width is not None):
                raise ValueError("--raw and --width must be supplied together")
        source = args.source.read_text(encoding="utf-8")
        selection = request({"class": args.class_name, "method": args.method}, args.word_type)
        stage = "certificate"
        runner, receipt = load(source, selection, load_json(args.certificate))
        stage = "execution"
        if args.command == "inspect":
            result = {"receipt": receipt, "runtime": runner.describe()}
        else:
            value = runner.value(args.raw, args.width) if args.raw is not None else runner.run(args.bits).finish()
            result = {"status": "executed", "value": value, "receipt": receipt,
                      "width": args.width if args.raw is not None else len(args.bits)}
        code = 0
    except ExecutionLimit as exc:
        result, code = {"status": "execution_budget_exhausted", "error": str(exc)}, 2
    except Unsupported as exc:
        result, code = {"status": "unsupported", "error": str(exc)}, 2
    except (OSError, UnicodeError) as exc:
        result, code = {"status": "input_error", "error": str(exc)}, 64
    except (ValueError, TypeError, KeyError, IndexError, RecursionError) as exc:
        code = 3 if stage == "certificate" else 64
        result = {"status": "invalid_certificate" if code == 3 else "input_error", "error": str(exc)}
    except Exception as exc:
        result, code = {"status": "internal_error", "error": type(exc).__name__ + ": " + str(exc)}, 70
    result["target_checked"], result["lean_checked"] = False, False
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
