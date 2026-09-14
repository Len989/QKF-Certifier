"""python -m research.observations.context_cli {descending,check-descending,derive,check}"""
import argparse
import json
from pathlib import Path

from .context_checker import check


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    derive = sub.add_parser("derive")
    derive.add_argument("model", type=Path)
    derive.add_argument("certificate", type=Path)
    derive.add_argument("--max-states", type=int, default=4096)
    derive.add_argument("--max-product", type=int, default=65536)
    verify = sub.add_parser("check")
    verify.add_argument("model", type=Path)
    verify.add_argument("certificate", type=Path)
    descending = sub.add_parser("descending")
    descending.add_argument("output", type=Path)
    pinned = sub.add_parser("check-descending")
    pinned.add_argument("certificate", type=Path)
    args = parser.parse_args()
    try:
        if args.command in {"descending", "check-descending"}:
            from .descending_adapter import pinned_model
            data = pinned_model()
        else:
            data = json.loads(args.model.read_text())
        if args.command.startswith("check"):
            cert = json.loads(args.certificate.read_text())
            result = check(data, cert)
        else:
            from .context_producer import synthesize
            budgets = {} if args.command == "descending" else {
                "max_states": args.max_states, "max_product": args.max_product}
            proposal = synthesize(data, **budgets)
            if proposal["status"] != "candidate":
                print(json.dumps(proposal, indent=2))
                return 2
            cert = proposal["certificate"]
            result = check(data, cert)
            if args.command == "descending":
                args.output.mkdir(parents=True, exist_ok=False)
                for name, value in [("model", data), ("certificate", cert), ("result", result)]:
                    (args.output / f"{name}.json").write_text(json.dumps(value, indent=2) + "\n")
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
