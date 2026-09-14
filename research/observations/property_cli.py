"""Check a source factor against a separately supplied masked-upper target."""
import argparse
import json
from pathlib import Path

from .property_kernel import check
from .upper_spec import specification


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    template = sub.add_parser('spec'); template.add_argument('output', type=Path)
    template.add_argument('--claim', choices=['maximum', 'bound'], default='maximum')
    for name in ['derive', 'check']:
        cmd = sub.add_parser(name); cmd.add_argument('source', type=Path)
        cmd.add_argument('--source-certificate', type=Path, required=True)
        cmd.add_argument('--spec', type=Path, required=True)
        cmd.add_argument('--certificate', type=Path, required=True)
        if name == 'derive': cmd.add_argument('--max-states', type=int, default=8192)
    args = p.parse_args()
    try:
        if args.command == 'spec':
            with args.output.open('x') as f: f.write(json.dumps(specification(args.claim), indent=2) + '\n')
            print(json.dumps({'status': 'specification_written', 'claim': args.claim})); return 0
        source = args.source.read_text(); original = json.loads(args.source_certificate.read_text())
        spec = json.loads(args.spec.read_text())
        if args.command == 'derive':
            from .property_producer import synthesize
            proposal = synthesize(source, original, spec, max_states=args.max_states)
            if proposal['status'] != 'candidate':
                print(json.dumps(proposal)); return 2
            cert = proposal['certificate']
        else: cert = json.loads(args.certificate.read_text())
        result = check(source, original, spec, cert)
        if args.command == 'derive':
            with args.certificate.open('x') as f: f.write(json.dumps(cert, indent=2) + '\n')
        print(json.dumps(result, indent=2)); return 0 if result['status'] == 'certified' else 1
    except (ValueError, TypeError, KeyError, IndexError, OSError) as exc:
        print(json.dumps({'status': 'rejected', 'error': str(exc)})); return 3


if __name__ == '__main__': raise SystemExit(main())
