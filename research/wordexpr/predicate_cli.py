"""Terminal word-predicate CLI. Verification never imports a producer."""
import argparse
import json
from pathlib import Path

from .cli import load, save
from .frontend import Unsupported
from .predicate_checker import check


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prove', 'check'])
    p.add_argument('source')
    p.add_argument('--spec', required=True)
    p.add_argument('--certificate', required=True)
    a = p.parse_args(argv)
    try:
        raw = Path(a.source).read_bytes()
        if len(raw) > 2_000_000:
            raise ValueError('source byte budget')
        source, spec = raw.decode('utf-8'), load(a.spec)
        if a.action == 'prove':
            from .predicate_producer import Budget, derive
            try:
                cert, result = derive(source, spec)
            except Budget as exc:
                print(json.dumps({'status': 'budget_exhausted', 'error': str(exc)}))
                return 2
            save(a.certificate, cert)
        else:
            result = check(source, spec, load(a.certificate))
        print(json.dumps(result, sort_keys=True))
        return 0 if result['status'] == 'certified' else 1
    except Unsupported as exc:
        print(json.dumps({'status': 'source_unsupported', 'error': str(exc)}))
        return 2
    except (ValueError, TypeError, KeyError, IndexError, RecursionError) as exc:
        print(json.dumps({'status': 'invalid_certificate' if a.action == 'check' else 'input_error', 'error': str(exc)}))
        return 3 if a.action == 'check' else 64
    except (OSError, UnicodeError) as exc:
        print(json.dumps({'status': 'input_error', 'error': str(exc)}))
        return 64


if __name__ == '__main__':
    raise SystemExit(main())
