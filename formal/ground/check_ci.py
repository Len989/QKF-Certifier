"""Clean Lean build, reproducible exports, exact axiom audit and boundary checks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

from .fixtures import ROOT, regenerate
from .export import render
from .preserve import audit

REPO = ROOT.parents[1]
THEOREMS = ['walk_sound', 'path_sound', 'arguments_sound', 'event_sound', 'events_sound',
            'goals_sound', 'check_sound', 'typed_check_sound', 'checkRaw_sound', 'eval_typed',
            'typed_goal_sound', 'accepted_query_typed', 'accepted_goal_values']


def source_files():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(ROOT.rglob('*')) if p.is_file() and
            not {'.lake', '__pycache__'}.intersection(p.relative_to(ROOT).parts)}


def run(output, lake='lake', require_clean=False):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    before = source_files()
    preserved = audit()
    dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=REPO, text=True)
    if require_clean and dirty:
        raise ValueError('CI requires a clean tested commit')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    tree = subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=REPO, text=True).strip()
    commands = []

    def command(label, args, cwd=ROOT, accepted=True):
        process = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=300)
        text = process.stdout + process.stderr
        (output / (label + '.log')).write_text(text)
        commands.append({'label': label, 'args': args, 'returncode': process.returncode,
                         'expected_success': accepted})
        if (process.returncode == 0) != accepted:
            raise ValueError(label + ' unexpected result: ' + text[-3000:])
        return text

    try:
        version = command('version', [lake, 'env', 'lean', '--version'])
        if not re.search(r'Lean \(version 4\.33\.0,', version):
            raise ValueError('wrong Lean toolchain')
        fixture = regenerate(check_only=True)
        command('clean', [lake, 'clean'])
        command('build', [lake, 'build'])
        names = ['QKFGround.' + name for name in THEOREMS]
        names += ['QKFGround.Examples.' + c['name'] + ('_accepted' if c['expected'] else '_rejected')
                  for c in fixture['cases']]
        audit_file = output / 'Axioms.lean'
        audit_file.write_text('import Ground\nimport Examples\n' +
                              '\n'.join('#print axioms ' + n for n in names) + '\n')
        text = command('axioms', [lake, 'env', 'lean', str(audit_file)])
        axioms = {}
        for line in text.splitlines():
            m = re.fullmatch(r"'([^']+)' depends on axioms: \[(.*)\]", line)
            if m:
                axioms[m[1]] = m[2].split(', ') if m[2] else []
            m = re.fullmatch(r"'([^']+)' does not depend on any axioms", line)
            if m:
                axioms[m[1]] = []
        if set(axioms) != set(names) or any(set(a) - {'propext', 'Quot.sound'} for a in axioms.values()):
            raise ValueError('unexpected or incomplete axiom dependencies')
        # A serialized false proof must fail even if someone changes the expected
        # result of its exported theorem to true. Failure must be in decide.
        bad = json.loads((ROOT / 'evidence/reject_substituted_axiom.decoded.json').read_text())
        forged = output / 'ForgedExport.lean'
        forged.write_text('import Ground\nopen QKFGround\n' + render('forged', bad, accepted=True))
        log = command('forged-export-rejected', [lake, 'env', 'lean', str(forged)], accepted=False)
        if 'decide' not in log or 'error:' not in log:
            raise ValueError('forged export failed for an unrelated reason')
        # Ensure the build-style guard catches an unexpected proof assumption.
        for label, declaration in (
            ('proof-hole', 'theorem unsupported : False := by sorry'),
            ('new-axiom', 'axiom unproved : False\ntheorem unsupported : False := unproved'),
        ):
            control = output / (label + '.lean')
            control.write_text('import Ground\n' + declaration + '\n' +
                "/-- info: 'unsupported' does not depend on any axioms -/\n" +
                '#guard_msgs in\n#print axioms unsupported\n')
            log = command(label + '-rejected', [lake, 'env', 'lean', str(control)], accepted=False)
            if 'guard_msgs' not in log:
                raise ValueError('axiom control failed for an unrelated reason')
        for optimized in (False, True):
            command('python-optimized' if optimized else 'python-normal',
                    [sys.executable] + (['-O'] if optimized else []) +
                    ['-m', 'unittest', 'formal.ground.test_export'], cwd=REPO)
        if before != source_files() or preserved != audit():
            raise ValueError('source changed during formal validation')
        result = {'schema': 'qkf-ground-lean-validation-v1', 'status': 'passed',
                  'lean_version': version.strip(), 'revision': revision, 'tree': tree,
                  'source_dirty': bool(dirty), 'source_sha256': before, 'preservation': preserved,
                  'positive_dags': fixture['positive_count'], 'negative_dags': fixture['negative_count'],
                  'positive_goals': sum(len(c.get('positive_query_indices', [])) for c in fixture['cases']),
                  'general_theorems_audited': len(THEOREMS), 'axioms': axioms,
                  'integrity_controls': ['forged-export', 'proof-hole', 'new-axiom'],
                  'python_tests': 17, 'python_modes': ['normal', '-O'], 'commands': commands,
                  'scope': 'F1a: decoded positive typed ground-DAG soundness; F1b remains open'}
        with zipfile.ZipFile(output / 'checked_project.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in before:
                archive.write(ROOT / name, name)
        (output / 'RESULT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        return result
    except Exception as error:
        (output / 'FAILURE.json').write_text(json.dumps({'error': str(error), 'commands': commands}, indent=2))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--lake', default='lake')
    parser.add_argument('--require-clean', action='store_true')
    args = parser.parse_args()
    result = run(args.output, args.lake, args.require_clean)
    print(json.dumps({k: result[k] for k in ('status', 'positive_dags', 'negative_dags', 'positive_goals',
                                             'general_theorems_audited', 'python_tests')}, sort_keys=True))
