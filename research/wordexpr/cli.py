"""Research CLI; check never imports the producer or executes supplied source."""
import argparse
import json
from pathlib import Path

from .checker import check
from .frontend import Unsupported


def load(path):
    raw = Path(path).read_bytes()
    if len(raw) > 5_000_000:
        raise ValueError('JSON byte budget')

    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError('duplicate JSON key: ' + k)
            result[k] = v
        return result

    def invalid(value):
        raise ValueError('nonfinite JSON number: ' + value)

    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid)


def save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prove', 'check'])
    p.add_argument('source')
    p.add_argument('--spec', required=True)
    p.add_argument('--certificate', required=True)
    args = p.parse_args(argv)
    try:
        raw = Path(args.source).read_bytes()
        if len(raw) > 2_000_000:
            raise ValueError('source byte budget')
        source, spec = raw.decode('utf-8'), load(args.spec)
        if args.action == 'prove':
            from .producer import Budget, derive
            try:
                cert, result = derive(source, spec)
            except Budget as exc:
                print(json.dumps({'status': 'budget_exhausted', 'error': str(exc)}))
                return 2
            save(args.certificate, cert)
        else:
            result = check(source, spec, load(args.certificate))
        print(json.dumps(result, sort_keys=True))
        return 0 if result['status'] == 'certified' else 1
    except Unsupported as exc:
        print(json.dumps({'status': 'source_unsupported', 'error': str(exc)}))
        return 2
    except (ValueError, TypeError, KeyError, IndexError, RecursionError) as exc:
        print(json.dumps({'status': 'invalid_certificate' if args.action == 'check' else 'input_error', 'error': str(exc)}))
        return 3 if args.action == 'check' else 64
    except (OSError, UnicodeError) as exc:
        print(json.dumps({'status': 'input_error', 'error': str(exc)}))
        return 64


if __name__ == '__main__':
    raise SystemExit(main())
