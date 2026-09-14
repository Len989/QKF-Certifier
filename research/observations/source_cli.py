"""python -m research.observations.source_cli {java,derive,check-java,check}"""
import argparse
import json
from pathlib import Path

from .java_words import pinned_source
from .source_factor import check


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    derive = sub.add_parser('derive'); derive.add_argument('source', type=Path); derive.add_argument('certificate', type=Path)
    verify = sub.add_parser('check'); verify.add_argument('source', type=Path); verify.add_argument('certificate', type=Path)
    java = sub.add_parser('java'); java.add_argument('output', type=Path)
    pinned = sub.add_parser('check-java'); pinned.add_argument('certificate', type=Path)
    args = p.parse_args()
    try:
        source = pinned_source() if args.command in {'java', 'check-java'} else args.source.read_text()
        if args.command.startswith('check'):
            cert = json.loads(args.certificate.read_text())
        else:
            from .source_factor import synthesize
            result = synthesize(source)
            if result['status'] != 'candidate':
                print(json.dumps(result, indent=2)); return 2
            cert = result['certificate']
        result = check(source, cert)
        if args.command == 'java':
            args.output.mkdir(parents=True, exist_ok=False)
            for name, value in [('certificate', cert), ('result', result), ('source_ir', cert['word']['source_ir'])]:
                (args.output / f'{name}.json').write_text(json.dumps(value, indent=2) + '\n')
        elif args.command == 'derive':
            with args.certificate.open('x') as output: output.write(json.dumps(cert, indent=2) + '\n')
        print(json.dumps(result, indent=2)); return 0
    except (ValueError, TypeError, KeyError, IndexError, OSError) as exc:
        print(json.dumps({'status': 'rejected', 'error': str(exc)})); return 1


if __name__ == '__main__':
    raise SystemExit(main())
