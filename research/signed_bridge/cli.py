"""Build/check a source model; these commands never certify an external target."""
import argparse
import json
from pathlib import Path
from .checker import check, check_observations
from .model import CapacityExceeded, MAX_STATES, request
from research.wordexpr.frontend import Unsupported

MAX_JSON_BYTES = 8 * 1024 * 1024


def load(path):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate JSON key: " + key)
            out[key] = value
        return out
    def reject(value):
        raise ValueError("nonfinite JSON: " + value)
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("certificate JSON size budget")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=reject)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "check"))
    parser.add_argument("source", type=Path)
    parser.add_argument("--class", dest="class_name", required=True)
    parser.add_argument("--method", required=True)
    parser.add_argument("--word-type", choices=("int", "long"), required=True)
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--observations", type=Path,
                        help="check an existing observation certificate after source binding")
    parser.add_argument("--max-states", type=int, default=MAX_STATES)
    args = parser.parse_args(argv)
    try:
        if args.observations and args.command != "check":
            raise ValueError("--observations only checks existing certificates")
        if not 1 <= args.max_states <= MAX_STATES:
            raise ValueError("--max-states must be 1..64")
        source = args.source.read_text(encoding="utf-8")
        selection = request({"class": args.class_name, "method": args.method}, args.word_type)
        if args.command == "build":
            from .producer import derive
            cert, result = derive(source, selection, max_states=args.max_states)
            payload = json.dumps(cert, sort_keys=True, indent=2, allow_nan=False) + "\n"
            # Existing files, including symlinks, are never overwritten.
            with args.certificate.open("x", encoding="utf-8") as output:
                output.write(payload)
        else:
            cert = load(args.certificate)
            result = (check_observations(source, selection, cert, load(args.observations))
                      if args.observations else check(source, selection, cert))
        code = 0
    except CapacityExceeded as exc:
        result, code = {"status": "budget_exhausted", "error": str(exc)}, 2
    except Unsupported as exc:
        result, code = {"status": "unsupported", "error": str(exc)}, 2
    except (OSError, UnicodeError) as exc:
        result, code = {"status": "input_error", "error": str(exc)}, 64
    except (ValueError, KeyError, TypeError, IndexError, RecursionError) as exc:
        result, code = {"status": "invalid_certificate" if args.command == "check" else "input_error",
                        "error": str(exc)}, 3 if args.command == "check" else 64
    result["target_checked"] = False
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
