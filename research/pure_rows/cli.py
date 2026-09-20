"""Pure-row certifying research CLI; old word-program entry points are untouched."""
from __future__ import annotations
import argparse
import json
import sys
from .common import InputError, InvalidCertificate, encoded, read_json, write_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prove', 'check', 'explain', 'check-completion'))
    parser.add_argument('input')
    parser.add_argument('--proof', required=True)
    parser.add_argument('--budget', help='JSON file with explicit production limits')
    parser.add_argument('--left', type=int)
    parser.add_argument('--right', type=int)
    parser.add_argument('--horizon', type=int, default=2)
    args = parser.parse_args(argv)
    try:
        data = read_json(args.input)
        if args.command == 'prove':
            from .producer import prove
            result, proof = prove(data, None if args.budget is None else read_json(args.budget))
            if proof is not None:
                write_json(args.proof, proof)
            print(encoded(result).decode('utf-8'))
            return 0 if proof is not None else 2
        if args.budget is not None:
            raise InputError('production budget does not change a replay obligation')
        try:
            proof = read_json(args.proof)
        except (ValueError, TypeError) as exc:
            raise InvalidCertificate(str(exc)) from exc
        from .checker import check, check_completion, explain
        if args.command == 'check':
            result = check(data, proof)
        elif args.command == 'check-completion':
            result = check_completion(data, proof)
        else:
            if args.left is None or args.right is None:
                raise InputError('explain requires both label indices')
            result = explain(data, proof, args.left, args.right, args.horizon)
        print(encoded(result).decode('utf-8'))
        return 0
    except InvalidCertificate as exc:
        print(json.dumps(dict(status='invalid_certificate', error=str(exc))), file=sys.stderr)
        return 3
    except (InputError, ValueError, OSError) as exc:
        print(json.dumps(dict(status='input_error', error=str(exc))), file=sys.stderr)
        return 64


if __name__ == '__main__':
    raise SystemExit(main())
