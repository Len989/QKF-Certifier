"""Pin inherited bytes and the validated lower development before the main run."""
import argparse,datetime,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inherited():
    records=json.loads((ROOT/'INHERITED_FILES.json').read_text())['files']
    for name,r in records.items():
        p=ROOT/name
        if p.stat().st_size!=r['bytes'] or sha(p)!=r['sha256']:raise ValueError('Changed inherited file '+name)
    return len(records)
def verify():
    n=inherited();files=json.loads((ROOT/'FREEZE.json').read_text())['files']
    for name,h in files.items():
        if sha(ROOT/name)!=h:raise ValueError('Changed frozen file '+name)
    return dict(inherited_files=n,frozen_files=len(files))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--create',action='store_true');a=p.parse_args()
    if a.create:
        inherited()
        for name in ['validation/semantics/results.json','validation/proofs/results.json']:
            if json.loads((ROOT/name).read_text())['status']!='passed':raise ValueError('Required validation '+name)
        files=[p for p in sorted(ROOT.rglob('*')) if p.is_file() and not set(p.relative_to(ROOT).parts)&{'__pycache__','results','audit','reproduction','papers','prior_stage'} and p.name not in {'FREEZE.json','PACKAGE_MANIFEST.json','DATA_MANIFEST.json','EXPERIMENT_DATA.tar.xz','RESTORE_CHECK.json'} and p.suffix not in {'.pyc','.tmp'}]
        # All inherited files are pinned separately, including inherited results/freezes.
        record=dict(schema='qkf-lower-development-freeze-v1',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),context='Known Graal development; no new holdout',files={str(p.relative_to(ROOT)):sha(p) for p in files})
        with (ROOT/'FREEZE.json').open('x') as f:json.dump(record,f,indent=2);f.write('\n')
    print(json.dumps(verify()))
