"""Replay saved source, word, joint and finite-theory proofs in fresh processes."""
import argparse, json, shutil, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent


def run(output):
    if sys.flags.optimize:
        raise ValueError('Use ordinary Python; do not disable assertions')
    output = output.resolve(); output.mkdir(parents=True, exist_ok=False); records = []
    for mode, operation in [('control','or'), ('joint','and'), ('joint','or')]:
        source = ROOT / 'results' / mode / operation; dest = output / mode / operation
        (dest / 'word/certificates').mkdir(parents=True)
        for name in ['source.json', 'source_certificate.json', 'word/certificates/' + operation.capitalize() + '.json']:
            shutil.copyfile(source / name, dest / name)
        records.append(phase('replay', mode, operation, dest))
    for worker, operation in [('joint', 'joint_queries'), ('theory', 'paper_row')]:
        dest = output / ('strict_' + worker); dest.mkdir()
        records.append(phase(worker, 'joint', operation, dest))
    result = dict(status='passed', fresh_processes=5, source_word_replays=3,
                  joint_certificates=28, finite_theory_replays=1, records=records)
    with (output / 'results.json').open('x') as f:
        json.dump(result, f, indent=2); f.write('\n')
    return result


def phase(worker, mode, operation, dest):
    subprocess.run([sys.executable, str(ROOT / 'step_run.py'), '--worker', worker,
                    '--mode', mode, '--operation', operation, '--output', str(dest)], check=True, timeout=75)
    record = json.loads((dest / (worker + '.json')).read_text())
    expected = 'proved_source_observation_and_whole_word_ssa' if worker == 'replay' else 'passed'
    if record['status'] != expected or record['search_modules_loaded'] != []:
        raise ValueError('Strict replay failed: ' + str(dest))
    return record


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    result = run(a.output)
    print(json.dumps({k:v for k,v in result.items() if k != 'records'}))
