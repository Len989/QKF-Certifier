"""Research CLI; check/apply/explain never import the builder."""
import argparse
import json
from pathlib import Path
from .contract import load_json, save_json
from .runtime import NotApplicable, OutsideDomain


def main(argv=None):
    parser = argparse.ArgumentParser(description='Experimental QKF checked summaries')
    parser.add_argument('operation', choices=('build', 'check', 'apply', 'assess', 'explain'))
    parser.add_argument('source')
    parser.add_argument('--request', required=True)
    parser.add_argument('--proof', required=True)
    parser.add_argument('--route')
    parser.add_argument('--limits')
    parser.add_argument('--work')
    parser.add_argument('--input', type=int)
    parser.add_argument('--width', type=int)
    parser.add_argument('--consumer')
    parser.add_argument('--goal', type=int, default=0)
    args = parser.parse_args(argv)
    try:
        path = Path(args.source)
        if path.stat().st_size > 2_000_000:
            raise ValueError('source byte budget')
        source, req = path.read_text(), load_json(args.request)
        if args.operation == 'build':
            if Path(args.proof).exists() or (args.work and Path(args.work).exists()):
                raise FileExistsError('output path must be new')
            from .producer import build
            proof, result, work = build(source, req, route=args.route,
                                        limits=None if args.limits is None else load_json(args.limits))
            if proof is not None:
                save_json(args.proof, proof)
            if args.work:
                save_json(args.work, work)
        else:
            if args.route is not None or args.limits is not None or args.work is not None:
                raise ValueError('route/limits/work apply only to build')
            from .checker import check
            checked = check(source, req, load_json(args.proof))
            if args.operation == 'check':
                result = checked.result()
            elif args.operation == 'apply':
                result = dict(status='applied', value=checked.apply(args.input, width=args.width))
            elif args.operation == 'assess':
                if args.consumer is None:
                    raise ValueError('assess requires --consumer')
                result = checked.assess(load_json(args.consumer))
            else:
                result = dict(status='explained', explanation=checked.explain(args.goal,
                    consumer=None if args.consumer is None else load_json(args.consumer)))
        print(json.dumps(result, sort_keys=True))
        return 0 if result['status'] in ('certified', 'verified_empty_domain', 'applied', 'explained') else 1
    except (NotApplicable, OutsideDomain) as exc:
        print(json.dumps(dict(status='unresolved' if isinstance(exc, NotApplicable) else 'unsupported',
                              reason=str(exc))))
        return 1
    except (ValueError, TypeError, KeyError, IndexError, OSError) as exc:
        print(json.dumps(dict(status='invalid_input' if args.operation == 'build' else 'invalid_certificate',
                              reason=str(exc))))
        return 2
