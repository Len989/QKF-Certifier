"""Infer/check/explain source observations, without supplying a property target."""
import argparse
import json
from pathlib import Path
from research.signed_bridge.cli import load
from research.signed_bridge.model import request
from research.wordexpr.frontend import Unsupported
from .checker import check


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("infer", "check", "explain"))
    parser.add_argument("source", type=Path)
    parser.add_argument("--class", dest="class_name", required=True)
    parser.add_argument("--method", required=True)
    parser.add_argument("--word-type", choices=("int", "long"), required=True)
    parser.add_argument("--certificate", type=Path, required=True)
    for flag, value in (("states", 64), ("observations", 63), ("pullbacks", 4096), ("classes", 64)):
        parser.add_argument("--max-" + flag, type=int, default=value)
    args = parser.parse_args(argv)
    try:
        text = args.source.read_text(encoding="utf-8")
        selection = request({"class": args.class_name, "method": args.method}, args.word_type)
        if args.command == "infer":
            from .producer import derive
            certificate, result = derive(text, selection, max_states=args.max_states,
                                         max_observations=args.max_observations,
                                         max_pullbacks=args.max_pullbacks, max_classes=args.max_classes)
            if certificate is None:
                print(json.dumps(result, sort_keys=True, allow_nan=False))
                return 2
            payload = json.dumps(certificate, sort_keys=True, indent=2, allow_nan=False) + "\n"
            with args.certificate.open("x", encoding="utf-8") as stream:
                stream.write(payload)
        else:
            certificate = load(args.certificate)
            if args.command == "check":
                result = check(text, selection, certificate)
            else:
                from .explain import explain
                result = explain(text, selection, certificate)
        code = 0
    except Unsupported as exc:
        result, code = {"status": "unsupported", "error": str(exc)}, 2
    except (OSError, UnicodeError) as exc:
        result, code = {"status": "input_error", "error": str(exc)}, 64
    except (ValueError, KeyError, TypeError, IndexError, RecursionError) as exc:
        code = 64 if args.command == "infer" else 3
        result = {"status": "input_error" if code == 64 else "invalid_certificate", "error": str(exc)}
    except Exception as exc:
        result, code = {"status": "internal_error", "error": type(exc).__name__ + ": " + str(exc)}, 70
    result["target_checked"] = False
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
