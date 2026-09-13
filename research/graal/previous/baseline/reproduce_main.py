"""Reproduce all five frozen development slots at a new output path."""
import argparse, json, subprocess, sys
from pathlib import Path
from step_run import ROOT, phase, save
from freeze_step import verify


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    if sys.flags.optimize:
        raise ValueError('Assertions must remain enabled')
    output = a.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    before = verify(); summaries = {}
    for mode in ['control', 'joint']:
        records = []
        for op in ['and', 'or', 'xor', 'add', 'sub']:
            dest = output / mode / op; source = phase(mode, op, 'source', dest)
            row = dict(operation=op, source=source, status=source['status'])
            if source['status'] == 'source_observation_produced':
                subprocess.run([sys.executable, str(ROOT / 'core/result_v2_run.py'), '--mode', 'observed',
                                '--case', op.capitalize(), '--output', str(dest / 'word')], check=True, timeout=150)
                word = json.loads((dest / 'word/summary.json').read_text())['records'][0]; row['word'] = word
                if word['status'] == 'proved_original_whole_all_positive_widths':
                    row['replay'] = phase(mode, op, 'replay', dest); row['status'] = row['replay']['status']
                else:
                    row['status'] = 'word_proof_incomplete'
            records.append(row)
        summaries[mode] = dict(selected=5, records=records)
        save(output / mode / 'summary.json', summaries[mode])
    phase('joint', 'joint_queries', 'joint', output / 'strict_joint')
    phase('joint', 'paper_row', 'theory', output / 'strict_theory')
    if verify() != before:
        raise ValueError('Changed frozen input')
    save(output / 'integrity.json', before)
    print(json.dumps({m: {'selected': 5, 'statuses': {r['operation']:r['status'] for r in s['records']}}
                      for m,s in summaries.items()}))
