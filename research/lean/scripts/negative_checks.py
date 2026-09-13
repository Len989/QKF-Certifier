"""Optional developer checks: four isolated corruptions must fail in Lean.

Python 3 is needed only for this extra check, not for `lake build`.
The original project is never edited by this script.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def mutate(root, name):
    relative = 'QKF/RowRules.lean' if name == 'proof_placeholder' else 'QKF/Data.lean'
    path = root / relative
    before = path.read_text(encoding='utf-8')
    if name == 'initial_state':
        after = before.replace('| 0 => ⟨true, .eq, .eq, .eq, true, true, false⟩',
                               '| 0 => ⟨false, .eq, .eq, .eq, true, true, false⟩', 1)
    elif name == 'transition_edge':
        after = before.replace('| 0, 0 => 0', '| 0, 0 => 1', 1)
    elif name == 'row_cell':
        prefix, rows = before.split('def rows ', 1)
        after = prefix + 'def rows ' + rows.replace('| 0, 1 => 1', '| 0, 1 => 0', 1)
    else:
        start = before.index('  induction proof with')
        end = before.index('\ntheorem forced_no_conflict', start)
        after = before[:start] + '  sorry\n' + before[end:]
    assert before != after
    path.write_text(after, encoding='utf-8')
    return {'file': relative,
            'original_sha256': hashlib.sha256(before.encode()).hexdigest(),
            'mutated_sha256': hashlib.sha256(after.encode()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lake', default='lake')
    args = parser.parse_args()
    lake = shutil.which(args.lake)
    if lake is None:
        raise SystemExit('Lake not found. First complete 00_START_HERE_RU.md.')
    results = []
    logs = ROOT / 'validation' / 'negative'
    logs.mkdir(parents=True, exist_ok=True)
    for name in ['initial_state', 'transition_edge', 'row_cell', 'proof_placeholder']:
        with tempfile.TemporaryDirectory(prefix='qkf_negative_', dir=ROOT.parent) as tmp:
            project = Path(tmp) / 'project'
            shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns(
                '.lake', 'validation', 'evidence', 'docs', 'scripts', 'CHECK_LOG.txt'))
            change = mutate(project, name)
            started = time.monotonic()
            process = subprocess.run([lake, 'build'], cwd=project, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True,
                                     encoding='utf-8', errors='replace', timeout=120)
            elapsed = round(time.monotonic() - started, 3)
            (logs / f'{name}.log').write_text(process.stdout, encoding='utf-8')
            expected = ('error: Audit.lean' if name == 'proof_placeholder'
                        else 'error: QKF/Checked.lean')
            rejected = process.returncode != 0 and expected in process.stdout
            if name != 'proof_placeholder':
                rejected = rejected and 'Tactic `decide`' in process.stdout
            results.append(dict(name=name, rejected_at_expected_gate=rejected,
                                exit_code=process.returncode, seconds=elapsed, **change))
            print(name + ': ' + ('rejected as expected' if rejected else 'FAILED'), flush=True)
    (logs / 'results.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    if not all(r['rejected_at_expected_gate'] for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
