"""python -m research.observations.ascending_cli {derive,check} SOURCE CERTIFICATE"""
import argparse
import json
from pathlib import Path

from .ascending_kernel import check


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['derive', 'check'])
    p.add_argument('source', type=Path); p.add_argument('certificate', type=Path)
    args = p.parse_args()
    try:
        source = args.source.read_text()
        if args.command == 'derive':
            from .ascending_producer import synthesize
            proposal = synthesize(source)
            if proposal['status'] != 'candidate': print(json.dumps(proposal)); return 2
            cert = proposal['certificate']
        else: cert = json.loads(args.certificate.read_text())
        result = check(source, cert)
        if args.command == 'derive':
            with args.certificate.open('x') as output: output.write(json.dumps(cert, indent=2) + '\n')
        print(json.dumps(result, indent=2)); return 0
    except (ValueError, TypeError, KeyError, IndexError, OSError) as exc:
        print(json.dumps({'status': 'rejected', 'error': str(exc)})); return 1


if __name__ == '__main__': raise SystemExit(main())
