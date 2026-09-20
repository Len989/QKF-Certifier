"""Research source-query CLI; check does not import native or closure discovery."""
import argparse
import json
from pathlib import Path
from .context import load_json, save_json, require


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prove', 'check'))
    parser.add_argument('source')
    parser.add_argument('request')
    parser.add_argument('certificate')
    parser.add_argument('--route', choices=('query', 'ordinary'), default='query')
    parser.add_argument('--fallback', action='store_true')
    args = parser.parse_args(argv)
    try:
        with open(args.source, 'rb') as stream:
            raw = stream.read(2_000_001)
        require(len(raw) <= 2_000_000, 'source byte budget')
        source = raw.decode('utf-8')
        request = load_json(args.request)
        if args.action == 'check':
            require(not args.fallback and args.route == 'query', 'check has no search options')
            from .checker import check
            result = check(source, request, load_json(args.certificate))
            print(json.dumps(result, sort_keys=True))
        else:
            require(not Path(args.certificate).exists(), 'certificate output already exists')
            from .producer import prove
            proof, result, work = prove(source, request, route=args.route, fallback=args.fallback)
            if proof is not None:
                save_json(args.certificate, proof)
            print(json.dumps({'result': result, 'work': work}, sort_keys=True))
        return 0 if result['status'] in ('certified', 'verified_empty_domain') else 1
    except (ValueError, TypeError, KeyError, OSError, RecursionError) as error:
        print(json.dumps({'status': 'input_or_certificate_error', 'error': str(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
