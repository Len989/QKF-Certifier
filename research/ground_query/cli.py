"""Research-only build/check interface; check never imports discovery code."""

import argparse
import json
from pathlib import Path
from .schema import load_json, save_json, require


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'check'))
    parser.add_argument('request')
    parser.add_argument('certificate')
    parser.add_argument('--mode', choices=('entailment', 'exact_threshold'), default='entailment')
    parser.add_argument('--horizon', type=int)
    args = parser.parse_args(argv)
    try:
        request = load_json(args.request)
        if args.action == 'build':
            require(not Path(args.certificate).exists(), 'output already exists')
            from .producer import prove
            certificate, stats = prove(request, args.mode, args.horizon)
            from .checker import check
            result = check(request, certificate)
            save_json(args.certificate, certificate)
            result = {'checked': result, 'telemetry': stats}
        else:
            require(args.horizon is None and args.mode == 'entailment',
                    'check takes the mode/horizon from the bound certificate')
            from .checker import check
            result = check(request, load_json(args.certificate))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, TypeError, KeyError, OSError, RecursionError) as error:
        print(json.dumps({'error': str(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
