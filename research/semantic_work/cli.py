"""Research command: measured control or independent semantic replay."""
import argparse
import json
import sys
from .contract import load_json, save_json, canonical


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('command', choices=('run', 'check'))
    p.add_argument('request')
    p.add_argument('--output', required=True, help='new output; run report includes the proof')
    p.add_argument('--proof', help='standalone certificate for check')
    a = p.parse_args(argv)
    try:
        from .run import run, check
        from pathlib import Path
        if Path(a.output).exists():
            raise FileExistsError('new output required')
        request = load_json(a.request)
        if a.command == 'run':
            if a.proof is not None:
                raise ValueError('run does not accept proof input')
            value = run(request)
            status = value['result']['status']
        else:
            if a.proof is None:
                raise ValueError('check requires standalone --proof')
            value = check(request, load_json(a.proof))
            status = value['status']
        save_json(a.output, value)
        print(json.dumps({'status': status, 'output': a.output}, sort_keys=True))
        return 0 if status == 'certified' else 1 if status == 'refuted' else 2
    except (ValueError, OSError, TypeError, KeyError, RecursionError) as exc:
        print(json.dumps({'status': 'input_or_certificate_error', 'error': str(exc)}), file=sys.stderr)
        return 64


if __name__ == '__main__':
    raise SystemExit(main())
