"""Replay the new universal certificate and preceding whole-program proofs at a new path."""
import argparse,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent


def run(out):
    if sys.flags.optimize:raise ValueError('Assertions must remain enabled')
    out=out.resolve();out.mkdir(parents=True,exist_ok=False);current=out/'universal_upper';current.mkdir()
    for name in ['producer.json','certificate.json']:
        shutil.copyfile(ROOT/'results/main/universal_upper'/name,current/name)
    subprocess.run([sys.executable,str(ROOT/'run_step.py'),'--phase','replay','--output',str(current)],check=True,timeout=70)
    proof=json.loads((current/'replay.json').read_text())
    if proof['status']!='proved_universal_upper_contract' or proof['search_modules_loaded']:raise ValueError('Universal strict replay')
    subprocess.run([sys.executable,str(ROOT/'baseline/replay_saved.py'),'--output',str(out/'preceding_proofs')],check=True,timeout=160)
    previous=json.loads((out/'preceding_proofs/results.json').read_text())
    if previous['status']!='passed':raise ValueError('Preceding strict replays')
    result=dict(status='passed',fresh_proof_processes=1+previous['fresh_processes'],universal_upper=proof,
                preceding_source_word_replays=previous['source_word_replays'],preceding_joint_certificates=previous['joint_certificates'],
                preceding_finite_theory_replays=previous['finite_theory_replays'])
    with (out/'results.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();result=run(a.output)
    print(json.dumps({k:v for k,v in result.items() if k!='universal_upper'}))
