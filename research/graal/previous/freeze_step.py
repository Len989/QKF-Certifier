"""Integrity of the exact preceding project and the validated new development version."""
import argparse,datetime,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def inherited():
    records=json.loads((ROOT/'INHERITED_FILES.json').read_text())['files']
    for name,r in records.items():
        p=ROOT/name
        if p.stat().st_size!=r['bytes'] or sha(p)!=r['sha256']:raise ValueError('Changed inherited file: '+name)
    return len(records)


def verify():
    count=inherited();frozen=json.loads((ROOT/'FREEZE.json').read_text())
    for name,h in frozen['files'].items():
        if sha(ROOT/name)!=h:raise ValueError('Changed frozen file: '+name)
    return dict(inherited_files=count,frozen_files=len(frozen['files']))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--create',action='store_true');a=p.parse_args()
    if a.create:
        inherited()
        for name in ['validation/semantics_v2/results.json','validation/certificates_v1/results.json']:
            if json.loads((ROOT/name).read_text())['status']!='passed':raise ValueError('Validation required: '+name)
        files=[p for p in sorted(ROOT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
               and p.suffix not in {'.pyc','.tmp'} and p!=ROOT/'FREEZE.json']
        value=dict(schema='qkf-universal-upper-development-freeze-v1',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   context='Development on pinned known Graal source; not a new holdout',
                   files={str(p.relative_to(ROOT)):sha(p) for p in files})
        with (ROOT/'FREEZE.json').open('x') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(verify()))
