"""Bind implementation, mechanism tests and protocol before corpus evaluation."""
import argparse,datetime,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def verify():
    frozen=json.loads((ROOT/'FREEZE.json').read_text())
    baseline=json.loads((ROOT/'BASELINE_SHA256.json').read_text())
    for n,h in frozen['files'].items():
        if sha(ROOT/n)!=h:raise ValueError('frozen file changed: '+n)
    for n,h in baseline['files'].items():
        if sha(ROOT/n)!=h:raise ValueError('inherited file changed: '+n)
    return dict(frozen_files=len(frozen['files']),baseline_files=len(baseline['files']))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--create',action='store_true');a=p.parse_args()
    if a.create:
        paths=[p for p in sorted(ROOT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
               and p.suffix not in {'.pyc','.tmp'} and p.name!='FREEZE.json']
        data=dict(schema='qkf-requested-result-observation-freeze-v1',
                  utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  files={str(p.relative_to(ROOT)):sha(p) for p in paths})
        with (ROOT/'FREEZE.json').open('x') as f:json.dump(data,f,indent=2);f.write('\n')
    print(json.dumps(verify()))
