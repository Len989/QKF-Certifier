"""Complete ZIP, exact previous archive, and full byte readback verification."""
import hashlib,io,json,tarfile,zipfile
from pathlib import Path
from freeze_context import verify
ROOT=Path(__file__).resolve().parent
ARCHIVE=ROOT.parent/'QKF_CONTEXT_OBSERVATIONS_2026-09-13.zip'
PRIOR='prior_stage/QKF_BOUNDARY_ACTIONS_2026-09-13.zip'
PRIOR_HASH='a231c3fa18bde0c28149cb098d6006f0b29ee186e9a2c37b6310ed9de1245884'


def sha(b):return hashlib.sha256(b).hexdigest()


if __name__=='__main__':
    verify();assert json.loads((ROOT/'audit/AUDIT.json').read_text())['status']=='passed'
    assert sha((ROOT/PRIOR).read_bytes())==PRIOR_HASH
    for n,h in json.loads((ROOT/'audit/FINAL_OUTPUTS_SHA256.json').read_text()).items():
        assert sha((ROOT/n).read_bytes())==h,n
    data_files=[p for folder in ['results','development','validation'] for p in sorted((ROOT/folder).rglob('*'))
                if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.tmp'}]
    data_entries={str(p.relative_to(ROOT)):dict(bytes=p.stat().st_size,sha256=sha(p.read_bytes())) for p in data_files}
    data_archive=ROOT/'EXPERIMENT_DATA.tar.xz'
    with tarfile.open(data_archive,'w:xz',preset=9) as tar:
        for p in data_files:
            info=tar.gettarinfo(str(p),arcname=str(p.relative_to(ROOT)))
            info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0
            with p.open('rb') as f:tar.addfile(info,f)
    data_manifest=dict(schema='qkf-packed-experiment-data-v1',files=data_entries,archive_sha256=sha(data_archive.read_bytes()))
    (ROOT/'DATA_MANIFEST.json').write_text(json.dumps(data_manifest,indent=2)+'\n')
    print('Packed',len(data_entries),'data files:',data_archive.stat().st_size,'bytes',flush=True)
    files=[p for p in sorted(ROOT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
           and p.suffix not in {'.pyc','.tmp'} and p.relative_to(ROOT).parts[0] not in {'reproduction','results','development','validation'}
           and p.name!='PACKAGE_MANIFEST.json']
    entries={str(p.relative_to(ROOT)):dict(bytes=p.stat().st_size,sha256=sha(p.read_bytes())) for p in files}
    manifest=dict(schema='qkf-context-observations-complete-package-v1',files=entries,
                  prior_archive_sha256=PRIOR_HASH,
                  scope='current frozen runtime, every final result and failure, development evidence, reports, both papers, exact full prior archive',
                  compression='standard deflated ZIP; experiment result data use one lossless tar.xz member, restored by restore_data.py',
                  packed_data_files=len(data_entries),packed_data_manifest='DATA_MANIFEST.json')
    mp=ROOT/'PACKAGE_MANIFEST.json';mp.write_text(json.dumps(manifest,indent=2)+'\n')
    building=ARCHIVE.with_suffix('.building.zip')
    with zipfile.ZipFile(building,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for i,p in enumerate(files+[mp]):
            method=zipfile.ZIP_STORED if p.suffix in {'.zip','.xz'} else zipfile.ZIP_DEFLATED
            z.write(p,ROOT.name+'/'+str(p.relative_to(ROOT)),compress_type=method)
        print('Written',len(files)+1,'entries; verifying',flush=True)
    with zipfile.ZipFile(building) as z:
        assert z.testzip() is None and len(z.infolist())==len(entries)+1
        for n,r in entries.items():
            data=z.read(ROOT.name+'/'+n)
            assert len(data)==r['bytes'] and sha(data)==r['sha256'],n
        assert json.loads(z.read(ROOT.name+'/PACKAGE_MANIFEST.json'))==manifest
        with tarfile.open(fileobj=io.BytesIO(z.read(ROOT.name+'/EXPERIMENT_DATA.tar.xz')),mode='r:xz') as tar:
            assert len(tar.getmembers())==len(data_entries)
            for member in tar.getmembers():
                assert member.isfile() and member.name in data_entries
                data=tar.extractfile(member).read();r=data_entries[member.name]
                assert len(data)==r['bytes'] and sha(data)==r['sha256'],member.name
    building.replace(ARCHIVE)
    result=dict(path=str(ARCHIVE),bytes=ARCHIVE.stat().st_size,sha256=sha(ARCHIVE.read_bytes()),
                files=len(entries)+1,packed_data_files=len(data_entries),all_entries_read_back_verified=True)
    (ROOT.parent/'QKF_CONTEXT_OBSERVATIONS_2026-09-13.archive.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
