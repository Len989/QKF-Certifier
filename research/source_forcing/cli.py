"""Separate experimental local-cell CLI; the installed qkf command is unchanged."""
import argparse
import json
from pathlib import Path
from .context import SOURCE_LIMIT, need, read_json, write_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prove', 'check'))
    parser.add_argument('source', type=Path)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--proof', type=Path, required=True)
    parser.add_argument('--route', choices=('forcing', 'no_saturation', 'direct_seeds', 'direct_cell'), default='forcing')
    args = parser.parse_args(argv)
    try:
        need(args.source.stat().st_size <= SOURCE_LIMIT, 'source byte limit')
        source, request = args.source.read_text(), read_json(args.request)
        if args.command == 'prove':
            from .producer import prove
            cert, result, work = prove(source, request, route=args.route)
            if cert is not None:
                write_json(args.proof, cert)
            print(json.dumps(dict(result=result, work=work), sort_keys=True))
        else:
            from .checker import check
            result = check(source, request, read_json(args.proof))
            print(json.dumps(result, sort_keys=True))
        return 0 if result['status'] == 'certified' else 1
    except (ValueError, OSError) as exc:
        print(json.dumps(dict(status='invalid', reason=str(exc))))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
