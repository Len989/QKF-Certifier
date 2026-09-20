"""Versioned reduction/model/observation commands, with no target argument."""
import argparse
import json
from pathlib import Path
from research.signed_bridge.cli import load
from research.signed_bridge.model import CapacityExceeded, request
from research.wordexpr.frontend import MAX_SOURCE, Unsupported
from . import bridge, checker, rules


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("reduce", "build", "infer", "check"))
    p.add_argument("source", type=Path)
    p.add_argument("--class", dest="class_name", required=True)
    p.add_argument("--method", required=True)
    p.add_argument("--word-type", choices=("int", "long"), required=True)
    p.add_argument("--certificate", type=Path, required=True)
    p.add_argument("--max-states", type=int, default=64)
    p.add_argument("--max-steps", type=int, default=512)
    p.add_argument("--max-observations", type=int, default=63)
    args = p.parse_args(argv)
    try:
        with args.source.open("rb") as stream:
            raw = stream.read(MAX_SOURCE + 1)
        if len(raw) > MAX_SOURCE:
            raise ValueError("source byte budget")
        source = raw.decode("utf-8")
        selection = request({"class": args.class_name, "method": args.method}, args.word_type)
        if args.command == "check":
            certificate = load(args.certificate)
            schema = certificate.get("schema") if type(certificate) is dict else None
            check = {rules.SCHEMA: checker.check, bridge.MODEL_SCHEMA: bridge.check_model,
                     bridge.OBS_SCHEMA: bridge.check_observations}.get(schema)
            if check is None:
                raise ValueError("unsupported reduction proof schema")
            result, code = check(source, selection, certificate), 0
        else:
            if args.command == "reduce":
                from .producer import derive
                certificate, result = derive(source, selection, max_steps=args.max_steps)
            else:
                action = bridge.build if args.command == "build" else bridge.infer
                extra = {"max_observations": args.max_observations} if args.command == "infer" else {}
                certificate, result = action(source, selection, max_states=args.max_states,
                                             max_steps=args.max_steps, **extra)
            code = 0 if certificate is not None else 2
            if certificate is not None:
                with args.certificate.open("x", encoding="utf-8") as stream:
                    stream.write(json.dumps(certificate, sort_keys=True, indent=2, allow_nan=False) + "\n")
    except CapacityExceeded as exc:
        result, code = {"status": "budget_exhausted", "reason": str(exc)}, 2
    except Unsupported as exc:
        result, code = {"status": "unsupported", "reason": str(exc)}, 2
    except (OSError, UnicodeError) as exc:
        result, code = {"status": "input_error", "reason": str(exc)}, 64
    except (ValueError, KeyError, TypeError, IndexError, RecursionError) as exc:
        checking = args.command == "check"
        result, code = {"status": "invalid_certificate" if checking else "input_error", "reason": str(exc)}, 3 if checking else 64
    result["target_checked"], result["lean_checked"] = False, False
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
