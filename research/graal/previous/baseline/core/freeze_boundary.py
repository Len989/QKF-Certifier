"""Freeze mechanism/protocol/development before the full experiments."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def verify():
    data=json.loads((ROOT/'FREEZE.json').read_text())
    for n,h in data['files'].items():
        if sha(ROOT/n)!=h:raise ValueError('frozen file changed: '+n)
    return len(data['files'])


if __name__=='__main__':
    if '--verify' in sys.argv:print(verify());raise SystemExit()
    assert not (ROOT/'FREEZE.json').exists()
    for n,h in json.loads((ROOT/'BASELINE_SHA256.json').read_text()).items():assert sha(ROOT/n)==h,n
    fs={str(p.relative_to(ROOT)):sha(p) for p in sorted(ROOT.rglob('*')) if p.is_file()
        and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.tmp'}
        and p.relative_to(ROOT).parts[0] not in {'results','reproduction'}}
    (ROOT/'FREEZE.json').write_text(json.dumps(dict(schema='qkf-boundary-actions-freeze-v1',files=fs,
        before_full_representations=True,before_full_corpus=True,
        development='first 80 representatives and Smin/Umax/UaddSat source probes; not an unseen holdout'),indent=2)+'\n')
    print('Frozen files:',verify())
