"""Fail-closed, bounded fresh Lean build/axiom audit/negative controls for run 4.

No automatic downloads and no reuse of historical successful build logs.
A successful Python export is not a successful Lean proof. The result records
unavailable/timeout/build failure separately and is accepted only after all gates.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time

from .lean_target_export import ROOT, export_all
from .model import require

PROJECT = ROOT / 'research/lean_targets'
THEOREMS = (
    'QKFTarget.columns_complete', 'QKFTarget.closed_certificate_sound',
    'QKFTarget.atom_numerical_step', 'QKFTarget.numerical_formula_all_widths',
    'QKFTarget.cyclic_successor_all_widths', 'QKFTarget.cyclic_extrema_characterization',
    'QKFTarget.Original.accepted', 'QKFTarget.Original.numerical_all_widths',
    'QKFTarget.Irrelevant.accepted', 'QKFTarget.Irrelevant.numerical_all_widths',
)
ALLOWED_AXIOMS = {'propext', 'Quot.sound'}


def audit_output(text):
    """Require complete output for the expected names; reject any hidden axiom."""
    result = {}
    for name in THEOREMS:
        escaped = re.escape(name)
        matches = list(re.finditer("'" + escaped + "' (?:does not depend on any axioms|depends on axioms: \\[([^\\]]*)\\])", text))
        require(len(matches) == 1, 'missing or repeated Lean audit entry: ' + name)
        raw = matches[0].group(1)
        axioms = [] if raw is None else [v.strip() for v in raw.split(',') if v.strip()]
        require(set(axioms) <= ALLOWED_AXIOMS, 'unexpected Lean axioms: ' + name + ': ' + str(axioms))
        result[name] = axioms
    return result


def run_command(command, cwd, timeout):
    """Bound a process AND terminate its child process group on POSIX timeout."""
    if timeout <= 0:
        return {'status': 'timeout', 'returncode': None, 'stdout': '', 'stderr': 'total time budget exhausted'}
    started = time.monotonic()
    try:
        child = subprocess.Popen(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, start_new_session=os.name == 'posix')
    except OSError as exc:
        return {'status': 'unavailable', 'returncode': None, 'stdout': '', 'stderr': str(exc)}
    try:
        out, err = child.communicate(timeout=timeout)
        status = 'success' if child.returncode == 0 else 'failed'
    except subprocess.TimeoutExpired:
        if os.name == 'posix':
            try: os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        else:
            child.kill()
        out, err = child.communicate()
        status = 'timeout'
    return {'status': status, 'returncode': child.returncode, 'stdout': out, 'stderr': err,
            'elapsed_seconds': round(time.monotonic() - started, 6)}


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _copy(destination):
    shutil.copytree(PROJECT, destination, ignore=shutil.ignore_patterns('.lake', 'validation', '__pycache__'))


def negative_mutations(project):
    """Well-typed changes of data/rules, not syntax errors masquerading as rejection."""
    exported = (project / 'QKFTarget/Exported.lean').read_text(encoding='utf-8')
    core = (project / 'QKFTarget/Core.lean').read_text(encoding='utf-8')
    controls = [
        ('initial_state', 'QKFTarget/Exported.lean', '⟨states, edges, 0⟩', '⟨states, edges, 1⟩'),
        ('transition_edge', 'QKFTarget/Exported.lean', '| 0, 0 => 1\n', '| 0, 0 => 0\n'),
        ('source_cell', 'QKFTarget/Exported.lean', '| 0, 0 => (false, 0)', '| 0, 0 => (true, 0)'),
        ('target_substitution', 'QKFTarget/Exported.lean', 'target := ', 'target := (.conj (.literal false) '),
        ('column_projection', 'QKFTarget/Core.lean', 'if c.val == 0 then 0 else if c.val < 3 then 1',
         'if c.val == 0 then 1 else if c.val < 3 then 1'),
    ]
    result = []
    for name, path, old, new in controls:
        text = core if path.endswith('Core.lean') else exported
        require(old in text, 'negative control site: ' + name)
        if name == 'target_substitution':
            # Use a complete well-typed replacement of the FIRST program target.
            lines = text.splitlines()
            i = next(i for i, line in enumerate(lines) if line.startswith('    target := '))
            lines[i] = '    target := (.literal true) }'
            altered = '\n'.join(lines) + '\n'
        else:
            altered = text.replace(old, new, 1)
        result.append((name, path, altered))
    return result


def validate(output, *, timeout=180):
    require(type(timeout) is int and 1 <= timeout <= 900, 'validation budget 1..900 seconds')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    result = {'schema': 'qkf-run4-lean-validation-v1', 'status': 'not_checked', 'lean_checked': False,
              'required_version': '4.33.0', 'time_budget_seconds': timeout, 'commands': [],
              'scope': 'explicit exported factor and word goal only; not Python or Java frontend verification'}

    def finish(status, **extra):
        result.update(status=status, **extra, elapsed_seconds=round(time.monotonic() - start, 6))
        _write(output / 'RESULT.json', result)
        return result

    def command(name, args, cwd):
        remaining = timeout - (time.monotonic() - start)
        info = run_command(args, cwd, remaining)
        (output / (name + '.stdout.log')).write_text(info['stdout'], encoding='utf-8')
        (output / (name + '.stderr.log')).write_text(info['stderr'], encoding='utf-8')
        result['commands'].append({'name': name, 'argv': args, **{k: v for k, v in info.items()
                                                                 if k not in ('stdout', 'stderr')}})
        return info

    try:
        result['export'] = export_all(PROJECT / 'evidence', check_existing=True)
        require((PROJECT / 'QKFTarget/Exported.lean').read_bytes()
                == (PROJECT / 'evidence/Exported.lean').read_bytes(), 'actual generated module identity')
        result['lean_source_sha256'] = {p.relative_to(PROJECT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                        for p in sorted(PROJECT.rglob('*.lean')) if '.lake' not in p.parts}
        for path in PROJECT.rglob('*.lean'):
            if '.lake' in path.parts:
                continue
            text = path.read_text(encoding='utf-8')
            require(not re.search(r'\b(?:sorry|admit|native_decide|bv_decide)\b|^\s*(?:axiom|unsafe)\b',
                                  text, re.MULTILINE), 'forbidden proof shortcut in ' + str(path))
        result['static_shortcut_scan'] = 'passed; not a compiler or axiom audit'
        lake, lean = shutil.which('lake'), shutil.which('lean')
        if not lake or not lean:
            return finish('unavailable', reason='Lean/lake executable not installed; no theorem acceptance claimed')
        version = command('version', [lean, '--version'], PROJECT)
        if version['status'] != 'success': return finish(version['status'], stage='toolchain')
        if not re.search(r'\bversion 4\.33\.0\b', version['stdout']):
            return finish('wrong_toolchain', version_output=version['stdout'])
        with tempfile.TemporaryDirectory(prefix='qkf-run4-') as tmp:
            fresh = Path(tmp) / 'positive'
            _copy(fresh)
            built = command('build', [lake, 'build'], fresh)
            if built['status'] != 'success': return finish(built['status'], stage='fresh_build')
            audit = command('axioms', [lake, 'env', 'lean', 'Audit.lean'], fresh)
            if audit['status'] != 'success': return finish(audit['status'], stage='axiom_print')
            result['axioms'] = audit_output(audit['stdout'])
            controls = []
            for name, path, altered in negative_mutations(fresh):
                directory = Path(tmp) / name
                _copy(directory)
                (directory / path).write_text(altered, encoding='utf-8')
                check = command('negative_' + name, [lake, 'build'], directory)
                text = check['stdout'] + check['stderr']
                rejected = (check['status'] == 'failed' and 'decide' in text
                            and ('false' in text or 'failed' in text)
                            and not any(t in text for t in ('unknown identifier', 'unexpected token', 'file not found')))
                controls.append({'case': name, 'rejected_by_proof_check': rejected})
                if not rejected:
                    return finish('negative_control_failed', controls=controls, stage=name)
            # A real compiler/axiom negative control is attempted only AFTER
            # the unmodified project and its numerical theorems have passed.
            placeholder_dir = Path(tmp) / 'placeholder'
            _copy(placeholder_dir)
            pp = placeholder_dir / 'QKFTarget/Exported.lean'
            original = pp.read_text(encoding='utf-8')
            site = 'theorem accepted : Accepted machine program certificate := by decide'
            require(site in original, 'placeholder control theorem site')
            pp.write_text(original.replace(site, site.replace('by decide', 'by sorry'), 1), encoding='utf-8')
            pcb = command('negative_placeholder_build', [lake, 'build'], placeholder_dir)
            if pcb['status'] != 'success':
                return finish('negative_control_failed', stage='placeholder_build', controls=controls)
            pca = command('negative_placeholder_axioms', [lake, 'env', 'lean', 'Audit.lean'], placeholder_dir)
            if pca['status'] != 'success' or 'sorryAx' not in pca['stdout']:
                return finish('negative_control_failed', stage='placeholder_audit', controls=controls)
            try:
                audit_output(pca['stdout'])
            except ValueError:
                controls.append({'case': 'proof_placeholder', 'rejected_by_axiom_audit': True})
            else:
                return finish('negative_control_failed', stage='placeholder_accepted', controls=controls)
            # A separate audit-parser control prevents a placeholder from passing
            # merely because Lean allows it with a warning. It is NOT a Lean run.
            fabricated = '\n'.join("'" + t + "' depends on axioms: [sorryAx]" for t in THEOREMS)
            try:
                audit_output(fabricated)
            except ValueError:
                result['placeholder_audit_parser_control'] = 'rejected'
            else:
                return finish('audit_control_failed')
            if time.monotonic() - start > timeout:
                return finish('timeout', stage='total_budget', controls=controls)
            return finish('accepted', lean_checked=True, controls=controls)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        return finish('validation_error', error=str(exc))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=180, help='total compiler budget in seconds, at most 900')
    args = parser.parse_args()
    try:
        result = validate(args.output, timeout=args.timeout)
    except (ValueError, OSError) as exc:
        print(json.dumps({'status': 'input_error', 'lean_checked': False, 'error': str(exc)}))
        return 64
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'accepted' else 2 if result['status'] in {'unavailable', 'timeout'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
