"""python -m research.observations {derive,check,carry} ..."""
import argparse
import json
from pathlib import Path

from .checker import check


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    derive = sub.add_parser("derive")
    derive.add_argument("model", type=Path)
    derive.add_argument("certificate", type=Path)
    derive.add_argument("--max-observations", type=int, default=63)
    derive.add_argument("--max-pullbacks", type=int, default=4096)
    derive.add_argument("--row-encoding", choices=["complete", "atomic"], default="complete")
    verify = sub.add_parser("check")
    verify.add_argument("model", type=Path)
    verify.add_argument("certificate", type=Path)
    verify_carry = sub.add_parser("check-carry", help="Rebuild native semantics from pinned repository source")
    verify_carry.add_argument("certificate", type=Path)
    carry = sub.add_parser("carry")
    carry.add_argument("output", type=Path, help="New directory for model, certificate, result")
    args = parser.parse_args()
    try:
        if args.command == "check-carry":
            from .source_adapter import pinned_model
            result = check(pinned_model(), json.loads(args.certificate.read_text()))
        elif args.command == "check":
            result = check(json.loads(args.model.read_text()), json.loads(args.certificate.read_text()))
        else:
            from .producer import synthesize
            if args.command == "carry":
                from .source_adapter import pinned_model
                data = pinned_model()
                proposal = synthesize(data)
            else:
                data = json.loads(args.model.read_text())
                proposal = synthesize(data, max_observations=args.max_observations,
                                      max_pullbacks=args.max_pullbacks, row_encoding=args.row_encoding)
            if proposal["status"] != "candidate":
                print(json.dumps(proposal, indent=2))
                return 2
            cert = proposal["certificate"]
            result = check(data, cert)
            if args.command == "carry":
                args.output.mkdir(parents=True, exist_ok=False)
                for name, value in [("model.json", data), ("certificate.json", cert), ("result.json", result)]:
                    (args.output / name).write_text(json.dumps(value, indent=2) + "\n")
            else:
                with args.certificate.open("x") as output:
                    output.write(json.dumps(cert, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(json.dumps({"status": "rejected", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
