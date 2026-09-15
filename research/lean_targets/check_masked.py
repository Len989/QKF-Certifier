"""Real compiler/audit/semantic controls for the exact masked-word Lean bridge.

This driver is not a proof. Acceptance requires a fresh Lean build, the
protected theorem population and strict axiom audit, two-sided finite semantic
controls and an actual placeholder audit failure. Old source binding is replayed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from research.lean_targets.check_ci import (  # noqa: E402
    PROJECT, check_source_bindings, require, run_command,
)

PREFIX = 'QKFTarget.MaskedWords.'
THEOREMS = tuple(PREFIX + name for name in (
    'value_snoc', 'value_bound', 'executed_value', 'output_independent',
    'admissible_length', 'masked_width', 'column_for_bit', 'encode_columns',
    'masked_extrema', 'greater_exists_iff', 'trace_admissible',
    'exact_cyclic_successor', 'original_exact', 'irrelevant_exact',
    'cyclic_successor_unique', 'original_irrelevant_same',
))
CONTROLS = (
    'incompleteAlphabet', 'rivalReplacedBySeed', 'outputLeaksRival',
    'inputProjectionChanged', 'reversedBitOrder', 'wrapReturnsMaximum',
    'membershipSuffices', 'missingLengthConstraint',
)
ALLOWED_AXIOMS = {'propext', 'Quot.sound'}


def audit_output(text):
    records = {}
    for name in THEOREMS:
        pattern = "'" + re.escape(name) + "' (?:does not depend on any axioms|depends on axioms: \\[([^\\]]*)\\])"
        matches = list(re.finditer(pattern, text))
        require(len(matches) == 1, 'missing or repeated masked-word audit: ' + name)
        raw = matches[0].group(1)
        axioms = [] if raw is None else [v.strip() for v in raw.split(',') if v.strip()]
        require(set(axioms) <= ALLOWED_AXIOMS, 'unexpected masked-word axioms: ' + name)
        records[name] = axioms
    return records


def proof_rejected(info):
    text = (info['stdout'] + info['stderr']).lower()
    return (info['status'] == 'failed' and 'decide' in text and 'false' in text
            and not any(s in text for s in (
                'unknown identifier', 'unexpected token', 'file not found',
                'unknown module', 'maximum recursion', 'maximum number of steps',
            )))


def control_text(name, expected):
    require(name in CONTROLS or name == 'positiveExamples', 'known semantic control')
    require(type(expected) is bool, 'Boolean control expectation')
    return ('import QKFTarget.MaskedControls\n'
            'example : QKFTarget.MaskedWords.Controls.' + name + ' = '
            + ('true' if expected else 'false') + ' := by decide\n')


def validate(output, *, timeout=300):
    require(type(timeout) is int and 1 <= timeout <= 900, 'budget 1..900 seconds')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    result = {'schema': 'qkf-exact-masked-lean-validation-v1', 'status': 'not_checked',
              'lean_checked': False, 'required_version': '4.33.0',
              'time_budget_seconds': timeout, 'commands': [], 'controls': [],
              'scope': 'explicit factor and equally long legal bit lists; not Java/frontend or composition proof'}

    def finish(status, **details):
        result.update(status=status, **details, elapsed_seconds=round(time.monotonic() - started, 6))
        (output / 'RESULT.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        return result

    def command(name, args, cwd):
        info = run_command(args, cwd, timeout - (time.monotonic() - started))
        for stream in ('stdout', 'stderr'):
            (output / (name + '.' + stream + '.log')).write_text(info[stream], encoding='utf-8')
        result['commands'].append({'name': name, 'argv': args,
                                   **{k: v for k, v in info.items() if k not in ('stdout', 'stderr')}})
        print(json.dumps({'command': name, 'status': info['status']}), flush=True)
        return info

    try:
        result['source_binding'] = check_source_bindings()
        sources = {p.relative_to(PROJECT).as_posix(): p.read_bytes()
                   for p in sorted(PROJECT.rglob('*.lean')) if '.lake' not in p.parts}
        result['lean_source_sha256'] = {name: hashlib.sha256(raw).hexdigest() for name, raw in sources.items()}
        for name, raw in sources.items():
            require(not re.search(r'\b(?:sorry|admit|native_decide|bv_decide)\b|^\s*(?:axiom|unsafe)\b',
                                  raw.decode('utf-8'), re.MULTILINE), 'proof shortcut in ' + name)
        lean, lake = shutil.which('lean'), shutil.which('lake')
        if not lean or not lake:
            return finish('unavailable', reason='Lean/lake executable not installed')
        version = command('version', [lean, '--version'], PROJECT)
        if version['status'] != 'success':
            return finish(version['status'], stage='version')
        if not re.search(r'\bversion 4\.33\.0\b', version['stdout']):
            return finish('wrong_toolchain')
        result['lean_version'] = version['stdout'].strip()
        with tempfile.TemporaryDirectory(prefix='qkf-exact-masked-') as temporary:
            fresh = Path(temporary) / 'project'
            shutil.copytree(PROJECT, fresh, ignore=shutil.ignore_patterns('.lake', '__pycache__', 'validation'))
            built = command('fresh_build', [lake, 'build', 'QKFTarget.Masked', 'QKFTarget.MaskedControls'], fresh)
            if built['status'] != 'success':
                return finish(built['status'], stage='fresh_build')
            audit = command('axioms', [lake, 'env', 'lean', 'MaskedAudit.lean'], fresh)
            if audit['status'] != 'success':
                return finish(audit['status'], stage='audit')
            result['axioms'] = audit_output(audit['stdout'])
            probe = fresh / 'Probe.lean'
            probe.write_text(control_text('positiveExamples', True), encoding='utf-8')
            positive = command('positive_examples', [lake, 'env', 'lean', 'Probe.lean'], fresh)
            if positive['status'] != 'success':
                return finish('positive_control_failed')
            for name in CONTROLS:
                probe.write_text(control_text(name, False), encoding='utf-8')
                false = command(name + '_is_false', [lake, 'env', 'lean', 'Probe.lean'], fresh)
                if false['status'] != 'success':
                    return finish('negative_control_invalid', stage=name)
                probe.write_text(control_text(name, True), encoding='utf-8')
                wrong = command(name + '_cannot_be_true', [lake, 'env', 'lean', 'Probe.lean'], fresh)
                rejected = proof_rejected(wrong)
                result['controls'].append({'case': name, 'false_proved': True, 'false_claim_rejected': rejected})
                if not rejected:
                    return finish('negative_control_failed', stage=name)
            # Modify only an isolated temporary proof; the source project is untouched.
            masked = fresh / 'QKFTarget/Masked.lean'
            text = masked.read_text(encoding='utf-8')
            begin = text.index('theorem original_exact ')
            end = text.index('\ntheorem irrelevant_exact ', begin)
            declaration = text[begin:end].split(':= by', 1)[0]
            masked.write_text(text[:begin] + declaration + ':= by sorry\n' + text[end:], encoding='utf-8')
            placeholder = command('placeholder_build', [lake, 'build', 'QKFTarget.Masked'], fresh)
            if placeholder['status'] != 'success':
                return finish('placeholder_control_invalid', stage='build')
            bad_audit = command('placeholder_axioms', [lake, 'env', 'lean', 'MaskedAudit.lean'], fresh)
            require(bad_audit['status'] == 'success' and 'sorryAx' in bad_audit['stdout'],
                    'placeholder must reach the real axiom audit')
            try:
                audit_output(bad_audit['stdout'])
            except ValueError:
                result['placeholder_rejected_by_audit'] = True
            else:
                return finish('placeholder_control_failed')
        # Retain the actual unmodified Lean input bytes, not generated binaries.
        for name, raw in sources.items():
            destination = output / 'checked_sources' / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        return finish('accepted', lean_checked=True)
    except (ValueError, TypeError, KeyError, OSError, IndexError) as exc:
        return finish('rejected', error=str(exc))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args()
    try:
        result = validate(args.output, timeout=args.timeout)
    except (ValueError, OSError) as exc:
        print(json.dumps({'status': 'input_error', 'error': str(exc)}))
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['status'] == 'accepted' and result['lean_checked'] is True else 3


if __name__ == '__main__':
    raise SystemExit(main())
