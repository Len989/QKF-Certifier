"""Experimental cold-series proof and independent checking CLI."""
import argparse
import json
from pathlib import Path
from .context import load_json, save_json, require


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('prove', 'check'))
    p.add_argument('source', type=Path)
    p.add_argument('--request', type=Path, required=True)
    p.add_argument('--proof', type=Path, required=True)
    p.add_argument('--limits', type=Path)
    p.add_argument('--route', choices=('reuse', 'direct_cache', 'no_lemmas'), default='no_lemmas')
    args = p.parse_args(argv)
    try:
        require(args.source.stat().st_size <= 2_000_000, 'source byte budget')
        source, request = args.source.read_text(), load_json(args.request)
        if args.command == 'prove':
            from .producer import prove
            packet, result, work = prove(source, request, route=args.route,
                limits=None if args.limits is None else load_json(args.limits))
            if packet is not None:
                save_json(args.proof, packet)
            print(json.dumps(dict(result=result, work=work), sort_keys=True))
        else:
            from .checker import check
            result = dict(status='completed', goals=check(source, request, load_json(args.proof)))
            print(json.dumps(result, sort_keys=True))
        return 0 if result['status'] == 'completed' and all(g['status'] in ('certified', 'verified_empty_domain')
                    for g in result['goals']) else 1
    except (ValueError, OSError) as error:
        print(json.dumps(dict(status='invalid', reason=str(error))))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
