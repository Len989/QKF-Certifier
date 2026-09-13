"""Integrity of inherited code and the validated development version."""
import argparse,datetime,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def inherited():
    files=json.loads((ROOT/'INHERITED_FILES.json').read_text())['files']
    for name,r in files.items():
        if sha(ROOT/name)!=r['sha256']:raise ValueError('changed inherited file: '+name)
    return len(files)
def verify():
    n=inherited();data=json.loads((ROOT/'FREEZE.json').read_text())
    for name,h in data['files'].items():
        if sha(ROOT/name)!=h:raise ValueError('changed frozen file: '+name)
    return dict(inherited_files=n,frozen_files=len(data['files']))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--create',action='store_true');a=p.parse_args()
    if a.create:
        inherited()
        for name in ['validation/joint_v1/results.json','validation/source_bridge_v1/results.json','theory/results.json']:
            assert json.loads((ROOT/name).read_text())['status']=='passed'
        files=[p for p in sorted(ROOT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.tmp'} and p.name!='FREEZE.json']
        data=dict(schema='qkf-joint-carriers-development-freeze-v1',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  context='Known Graal development regression; not a fresh holdout',files={str(p.relative_to(ROOT)):sha(p) for p in files})
        with (ROOT/'FREEZE.json').open('x') as f:json.dump(data,f,indent=2);f.write('\n')
    print(json.dumps(verify()))
