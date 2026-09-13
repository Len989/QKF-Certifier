"""Second frozen implementation; retain the first frozen run including failure."""
import argparse,datetime,hashlib,json
from pathlib import Path
from freeze_result import verify as verify_first
ROOT=Path(__file__).resolve().parent


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def verify():
    first=verify_first();f=json.loads((ROOT/'FREEZE_V2.json').read_text())
    for n,h in f['files'].items():
        if sha(ROOT/n)!=h:raise ValueError('second frozen file changed: '+n)
    return dict(frozen_files=len(f['files']),baseline_files=first['baseline_files'],first_frozen_files=first['frozen_files'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--create',action='store_true');a=p.parse_args()
    if a.create:
        files=[p for p in sorted(ROOT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
               and p.suffix not in {'.pyc','.tmp'} and p.name!='FREEZE_V2.json']
        data=dict(schema='qkf-result-observation-freeze-v2',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  reason='proposal generation must inspect the normalized node kind before indexing its amount',
                  files={str(p.relative_to(ROOT)):sha(p) for p in files})
        with (ROOT/'FREEZE_V2.json').open('x') as f:json.dump(data,f,indent=2);f.write('\n')
    print(json.dumps(verify()))
