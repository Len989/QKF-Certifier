"""Package the complete current experiment and exact prior history; verify bytes."""
import hashlib,json,zipfile
from pathlib import Path
from freeze_boundary import verify
ROOT=Path(__file__).resolve().parent
ARCHIVE=ROOT.parent/'QKF_BOUNDARY_ACTIONS_2026-09-13.zip'
PRIOR='prior_stage/QKF_SEMANTIC_OBSERVATIONS_2026-09-13.zip'
PRIOR_HASH='4a103886f7e2ca874392be9887f1971c644439cb2a3dcf819321dc8de497e2e8'


def sha(data):return hashlib.sha256(data).hexdigest()


if __name__=='__main__':
    verify()
    assert json.loads((ROOT/'audit/AUDIT.json').read_text())['status']=='passed'
    assert sha((ROOT/PRIOR).read_bytes())==PRIOR_HASH
    for n,h in json.loads((ROOT/'FREEZE_V2.json').read_text())['files'].items():assert sha((ROOT/n).read_bytes())==h,n
    with zipfile.ZipFile(ROOT/PRIOR) as z:assert z.testzip() is None
    files=[p for p in sorted(ROOT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
        and p.suffix not in {'.pyc','.tmp'} and p.relative_to(ROOT).parts[0]!='reproduction' and p.name!='PACKAGE_MANIFEST.json']
    entries={str(p.relative_to(ROOT)):dict(bytes=p.stat().st_size,sha256=sha(p.read_bytes())) for p in files}
    manifest=dict(schema='qkf-boundary-actions-complete-package-v1',files=entries,prior_archive_sha256=PRIOR_HASH,
        scope='both current frozen revisions, every final result and failure, current runtime, both papers and exact complete previous archive')
    mp=ROOT/'PACKAGE_MANIFEST.json';mp.write_text(json.dumps(manifest,indent=2)+'\n')
    with zipfile.ZipFile(ARCHIVE,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in files+[mp]:z.write(p,ROOT.name+'/'+str(p.relative_to(ROOT)))
    with zipfile.ZipFile(ARCHIVE) as z:
        assert z.testzip() is None and len(z.infolist())==len(entries)+1
        for n,r in entries.items():
            b=z.read(ROOT.name+'/'+n);assert len(b)==r['bytes'] and sha(b)==r['sha256'],n
        assert json.loads(z.read(ROOT.name+'/PACKAGE_MANIFEST.json'))==manifest
    print(json.dumps(dict(path=str(ARCHIVE),bytes=ARCHIVE.stat().st_size,sha256=sha(ARCHIVE.read_bytes()),
        files=len(entries)+1,all_entries_read_back_verified=True),indent=2))
