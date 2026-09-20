"""Research compact bundles: independent target array, strict exclusive outputs."""
import argparse
import json
from pathlib import Path
import sys
from research.observations.model import require
from research.signed_context.io import load_json, save_json, source_text
from research.unified.checker import InvalidProof
from research.wordexpr.frontend import Unsupported
from .checker import load, export_legacy


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('command', choices=('prove', 'check', 'pair', 'export'))
    p.add_argument('source', type=Path)
    p.add_argument('--targets', required=True, type=Path)
    p.add_argument('--proof', required=True, type=Path)
    p.add_argument('--budget', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--left', type=int); p.add_argument('--right', type=int)
    p.add_argument('--index', type=int, default=0)
    a = p.parse_args(argv)
    try:
        require(a.command == 'prove' or a.budget is None, 'budgets are discovery only')
        require(a.command == 'pair' or (a.left is None and a.right is None), 'pair arguments only')
        require(a.command == 'export' or a.index == 0, 'export index only')
        require(a.command in {'pair', 'export'} or a.out is None, 'output only for pair/export')
        require(a.command != 'export' or a.out is not None, 'export requires --out')
        if a.command == 'prove': require(not a.proof.exists(), 'exclusive proof output')
        if a.out is not None: require(not a.out.exists(), 'exclusive output')
        source = source_text(a.source.read_text(encoding='utf-8')); targets = load_json(a.targets)
        if a.command == 'prove':
            from .producer import prove_many
            results, proof = prove_many(source, targets, budgets=load_json(a.budget) if a.budget else None)
            if proof is not None: save_json(a.proof, proof)
        else:
            try: packet = load_json(a.proof)
            except (ValueError, RecursionError) as exc: raise InvalidProof(str(exc)) from exc
            if a.command == 'export':
                proof = export_legacy(source, targets, packet, a.index)
                save_json(a.out, proof)
                print(json.dumps({'status': 'exported', 'target_result': proof['result']}, sort_keys=True))
                return 0
            ctx = load(source, targets, packet); results = ctx.results()
            if a.command == 'pair':
                out = ctx.explain_pair(a.left, a.right)
                if a.out is not None: save_json(a.out, out)
                print(json.dumps(out, sort_keys=True)); return 0
        statuses = [r['status'] for r in results]
        unresolved = any(s not in {'certified', 'refuted'} for s in statuses)
        status = 'unresolved' if unresolved else 'refuted' if 'refuted' in statuses else 'certified'
        print(json.dumps({'schema': 'qkf-compact-bundle-report-v1', 'status': status,
                          'claim': 'each listed target is checked separately', 'results': results}, sort_keys=True))
        return 2 if unresolved else 1 if status == 'refuted' else 0
    except InvalidProof as exc:
        status, code, message = 'invalid_certificate', 3, str(exc)
    except Unsupported as exc:
        status, code, message = 'unsupported', 2, str(exc)
    except (ValueError, TypeError, KeyError, IndexError, OSError, UnicodeError, RecursionError) as exc:
        status, code, message = 'input_error', 64, str(exc)
    except Exception as exc:
        status, code, message = 'internal_error', 70, type(exc).__name__
    print(json.dumps({'status': status, 'error': message}, sort_keys=True)); return code


if __name__ == '__main__': raise SystemExit(main())
