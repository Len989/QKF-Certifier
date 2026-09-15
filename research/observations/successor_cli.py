"""Independent ascending targets: spec / derive / check. Replay needs only Python."""
import argparse
import json
from pathlib import Path

from .successor_kernel import MAX_STATES, MAX_WITNESS, check
from .successor_spec import CLAIMS, specification


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_bytes().decode("utf-8"))


def write_json(path, value):
    data = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(data)


def main(argv=None):
    parser = Parser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    target = sub.add_parser("spec")
    target.add_argument("output", type=Path)
    target.add_argument("--claim", choices=CLAIMS, default="cyclic_successor")
    for command in ("derive", "check"):
        action = sub.add_parser(command)
        action.add_argument("source", type=Path)
        action.add_argument("--source-certificate", required=True, type=Path)
        action.add_argument("--spec", required=True, type=Path)
        action.add_argument("--certificate", required=True, type=Path)
        if command == "derive":
            action.add_argument("--max-states", type=int, default=MAX_STATES)
            action.add_argument("--max-witness", type=int, default=MAX_WITNESS)
    try:
        args = parser.parse_args(argv)
        if args.command == "spec":
            write_json(args.output, specification(args.claim))
            print(json.dumps({"status": "written", "claim": args.claim}))
            return 0
        source = args.source.read_bytes().decode("utf-8")
        source_certificate = read_json(args.source_certificate)
        spec = read_json(args.spec)
        if args.command == "derive":
            from .successor_producer import synthesize
            proposal = synthesize(source, source_certificate, spec,
                                  max_states=args.max_states, max_witness=args.max_witness)
            if proposal["status"] != "candidate":
                print(json.dumps(proposal))
                return 2
            certificate = proposal["certificate"]
        else:
            certificate = read_json(args.certificate)
        result = check(source, source_certificate, spec, certificate)
        if args.command == "derive":
            write_json(args.certificate, certificate)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "certified" else 1
    except (ValueError, TypeError, KeyError, IndexError, OSError, RecursionError) as exc:
        print(json.dumps({"status": "rejected", "error": str(exc)}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
