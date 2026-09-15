"""Bounded real Lean build, strict axiom audit and isolated negative controls.

Uses the existing main-branch source checker to bind the two exported machines.
This bridge remains Python code, not a formal proof about the Java frontend.
Only the complete compiler/audit/negative-control route returns accepted.
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
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / 'research/lean_targets'
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
THEOREMS = (
    'QKFTarget.columns_complete', 'QKFTarget.closed_certificate_sound',
    'QKFTarget.atom_numerical_step', 'QKFTarget.numerical_formula_all_widths',
    'QKFTarget.cyclic_successor_all_widths', 'QKFTarget.cyclic_extrema_characterization',
    'QKFTarget.Original.accepted', 'QKFTarget.Original.numerical_all_widths',
    'QKFTarget.Irrelevant.accepted', 'QKFTarget.Irrelevant.numerical_all_widths',
)
ALLOWED_AXIOMS = {'propext', 'Quot.sound'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit_output(text):
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
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            child.kill()
        out, err = child.communicate()
        status = 'timeout'
    return {'status': status, 'returncode': child.returncode, 'stdout': out, 'stderr': err,
            'elapsed_seconds': round(time.monotonic() - started, 6)}


def check_source_bindings():
    from research.observations.ascending_kernel import ALPHABET, Runner
    from research.observations.model import digest
    binding = json.loads((PROJECT / 'SOURCE_BINDINGS.json').read_text(encoding='utf-8'))
    text = (PROJECT / 'QKFTarget/Exported.lean').read_text(encoding='utf-8')
    require(hashlib.sha256(text.encode('utf-8')).hexdigest() == binding['exported_lean_sha256'],
            'exact exported Lean module identity')
    results = {}
    for label, name in (('Original', 'original'), ('Irrelevant', 'irrelevant_register')):
        entry = binding['sources'][name]
        base = ROOT / 'research/observations/evidence/ascending'
        source = (base / (name + '.java')).read_bytes().decode('utf-8')
        cert = json.loads((base / (name + '.certificate.json')).read_text(encoding='utf-8'))
        require(hashlib.sha256(source.encode('utf-8')).hexdigest() == entry['source_sha256'],
                'source identity: ' + name)
        require(digest(cert) == entry['source_certificate_sha256'], 'source certificate identity')
        runner = Runner(source, cert)
        count = len(cert['observations']['blocks'])
        lines = [f'def machine : Machine {count} :=',
                 f'  {{ initial := {runner.initial}, cell := fun s a =>',
                 '      match s.val, a.val with']
        for q in range(count):
            for a, symbol in enumerate(ALPHABET):
                y, following = runner.cells[q, symbol]
                value = 'true' if y == '1' else 'false'
                lines.append(f'      | {q}, {a} => ({value}, {following})')
        lines.append('      | _, _ => (false, 0) }')
        marker, ending = 'namespace ' + label + '\n', 'end ' + label
        require(text.count(marker) == 1 and text.count(ending) == 1, 'one source namespace')
        section = text.split(marker)[1].split(ending)[0]
        expected = '\n'.join(lines)
        require(section.count('def machine ') == 1 and section.count(expected) == 1,
                'every exported cell and initial state must match source replay: ' + name)
        results[name] = {'source_sha256': entry['source_sha256'],
                         'source_certificate_sha256': entry['source_certificate_sha256'],
                         'classes': count, 'cells': count * len(ALPHABET)}
    return {'status': 'source_factor_replayed', 'sources': results,
            'exported_lean_sha256': binding['exported_lean_sha256'],
            'scope': 'Python source bridge, not a Lean theorem about the Java frontend'}


def _copy(destination):
    shutil.copytree(PROJECT, destination, ignore=shutil.ignore_patterns('.lake', 'validation', '__pycache__'))


def negative_mutations(project):
    exported = (project / 'QKFTarget/Exported.lean').read_text(encoding='utf-8')
    core = (project / 'QKFTarget/Core.lean').read_text(encoding='utf-8')
    controls = [
        ('initial_state', 'QKFTarget/Exported.lean', '⟨states, edges, 0⟩', '⟨states, edges, 1⟩'),
        ('transition_edge', 'QKFTarget/Exported.lean', '| 0, 0 => 1\n', '| 0, 0 => 0\n'),
        ('source_cell', 'QKFTarget/Exported.lean', '| 0, 0 => (false, 0)', '| 0, 0 => (true, 0)'),
        ('target_substitution', 'QKFTarget/Exported.lean', 'target := ', 'target := '),
        ('column_projection', 'QKFTarget/Core.lean', 'if c.val == 0 then 0 else if c.val < 3 then 1',
         'if c.val == 0 then 1 else if c.val < 3 then 1'),
    ]
    result = []
    for name, path, old, new in controls:
        text = core if path.endswith('Core.lean') else exported
        require(old in text, 'negative control site: ' + name)
        if name == 'target_substitution':
            lines = text.splitlines()
            i = next(i for i, line in enumerate(lines) if line.startswith('    target := '))
            lines[i] = '    target := (.literal true) }'
            altered = '\n'.join(lines) + '\n'
        else:
            altered = text.replace(old, new, 1)
        result.append((name, path, altered))
    return result


def validate(output, *, timeout=300):
    require(type(timeout) is int and 1 <= timeout <= 900, 'validation budget 1..900 seconds')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    result = {'schema': 'qkf-run4-standalone-lean-validation-v1', 'status': 'not_checked', 'lean_checked': False,
              'required_version': '4.33.0', 'time_budget_seconds': timeout, 'commands': [],
              'scope': 'explicit exported factor and word goal only; not Python or Java frontend verification'}

    def finish(status, **extra):
        result.update(status=status, **extra, elapsed_seconds=round(time.monotonic() - start, 6))
        (output / 'RESULT.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        return result

    def command(name, args, cwd):
        remaining = timeout - (time.monotonic() - start)
        info = run_command(args, cwd, remaining)
        (output / (name + '.stdout.log')).write_text(info['stdout'], encoding='utf-8')
        (output / (name + '.stderr.log')).write_text(info['stderr'], encoding='utf-8')
        result['commands'].append({'name': name, 'argv': args, **{k: v for k, v in info.items()
                                                                 if k not in ('stdout', 'stderr')}})
        print(json.dumps({'command': name, 'status': info['status'], 'returncode': info['returncode']}), flush=True)
        return info

    try:
        result['source_binding'] = check_source_bindings()
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
        if version['status'] != 'success':
            return finish(version['status'], stage='toolchain')
        if not re.search(r'\bversion 4\.33\.0\b', version['stdout']):
            return finish('wrong_toolchain', version_output=version['stdout'])
        with tempfile.TemporaryDirectory(prefix='qkf-run4-') as tmp:
            fresh = Path(tmp) / 'positive'
            _copy(fresh)
            built = command('build', [lake, 'build'], fresh)
            if built['status'] != 'success':
                return finish(built['status'], stage='fresh_build')
            audit = command('axioms', [lake, 'env', 'lean', 'Audit.lean'], fresh)
            if audit['status'] != 'success':
                return finish(audit['status'], stage='axiom_print')
            result['axioms'] = audit_output(audit['stdout'])
            controls = []
            for name, path, altered in negative_mutations(fresh):
                directory = Path(tmp) / name
                _copy(directory)
                (directory / path).write_text(altered, encoding='utf-8')
                checked = command('negative_' + name, [lake, 'build'], directory)
                text = checked['stdout'] + checked['stderr']
                rejected = (checked['status'] == 'failed' and 'decide' in text
                            and ('false' in text or 'failed' in text)
                            and not any(t in text for t in ('unknown identifier', 'unexpected token', 'file not found')))
                controls.append({'case': name, 'rejected_by_proof_check': rejected})
                if not rejected:
                    return finish('negative_control_failed', controls=controls, stage=name)
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
            if time.monotonic() - start > timeout:
                return finish('timeout', stage='total_budget', controls=controls)
            return finish('accepted', lean_checked=True, controls=controls)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        return finish('validation_error', error=str(exc))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=300)
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
