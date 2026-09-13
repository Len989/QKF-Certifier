"""Lossless complete package with an exact prior archive and source inheritance."""
import hashlib,io,json,lzma,tarfile,zipfile
from pathlib import Path
from freeze_result_v2 import verify
ROOT=Path(__file__).resolve().parent
ARCHIVE=ROOT.parent/'QKF_RESULT_OBSERVATIONS_2026-09-13.zip'
PRIOR='prior_stage/QKF_CONTEXT_OBSERVATIONS_2026-09-13.zip'
PRIOR_HASH='4d2d70618c7fc663569b9b44fbfba280e020268119e70e6695c29f796f1622fa'
OLD_ROOT='qkf_context_observations_2026-09-13/'
DATA_FOLDERS={'results','results_v2','development','validation','baseline'}
GENERATED={'PACKAGE_MANIFEST.json','DATA_MANIFEST.json','INHERITED_FILES.json','EXPERIMENT_DATA.tar.xz'}


def sha(data):return hashlib.sha256(data).hexdigest()
def record(p):return dict(bytes=p.stat().st_size,sha256=sha(p.read_bytes()))
def save(n,data):(ROOT/n).write_text(json.dumps(data,indent=2)+'\n')


if __name__=='__main__':
    verify();audit=json.loads((ROOT/'audit/AUDIT.json').read_text())
    assert audit['status']=='passed' and audit['regressions']==[]
    assert sha((ROOT/PRIOR).read_bytes())==PRIOR_HASH
    for n,h in json.loads((ROOT/'audit/FINAL_OUTPUTS_SHA256.json').read_text()).items():
        assert sha((ROOT/n).read_bytes())==h,n
    files=[p for p in sorted(ROOT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
           and p.suffix not in {'.pyc','.tmp'} and p.relative_to(ROOT).parts[0]!='reproduction'
           and p.name not in GENERATED]
    inherited={};data=[];direct=[]
    with zipfile.ZipFile(ROOT/PRIOR) as z:
        old_names=set(z.namelist())
        for p in files:
            n=str(p.relative_to(ROOT))
            if p.relative_to(ROOT).parts[0] in DATA_FOLDERS:data.append(p)
            elif OLD_ROOT+n in old_names and z.read(OLD_ROOT+n)==p.read_bytes():
                inherited[n]={**record(p),'member':OLD_ROOT+n}
            else:direct.append(p)
    save('INHERITED_FILES.json',dict(schema='qkf-exact-source-inheritance-v1',archive=PRIOR,
        archive_sha256=PRIOR_HASH,files=inherited))
    # Adjacent versions of the same evidence share a compression dictionary;
    # every original byte and original relative path is retained.
    def order(p):
        n=p.relative_to(ROOT);parts=n.parts
        if parts[0] in {'results','results_v2'}:
            return ('results',parts[-1],*parts[1:-1],parts[0])
        return (parts[0],str(n))
    data.sort(key=order);data_records={str(p.relative_to(ROOT)):record(p) for p in data}
    packed=ROOT/'EXPERIMENT_DATA.tar.xz'
    with tarfile.open(packed,'w:xz',preset=9|lzma.PRESET_EXTREME) as tar:
        for p in data:
            info=tar.gettarinfo(str(p),arcname=str(p.relative_to(ROOT)))
            info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0
            with p.open('rb') as f:tar.addfile(info,f)
    save('DATA_MANIFEST.json',dict(schema='qkf-packed-experiment-data-v2',archive=packed.name,
         archive_sha256=sha(packed.read_bytes()),files=data_records))
    print('Packed',len(data),'data files:',packed.stat().st_size,'bytes; inherited',len(inherited),'files',flush=True)
    direct.extend(ROOT/n for n in ['INHERITED_FILES.json','DATA_MANIFEST.json','EXPERIMENT_DATA.tar.xz'])
    records={str(p.relative_to(ROOT)):record(p) for p in direct}
    manifest=dict(schema='qkf-result-observations-complete-package-v1',files=records,
        prior_archive_sha256=PRIOR_HASH,inherited_files=len(inherited),packed_data_files=len(data),
        inheritance_manifest='INHERITED_FILES.json',packed_data_manifest='DATA_MANIFEST.json',
        scope='both frozen runs including original failure, current code, every result, both papers, exact complete prior history',
        restoration='python restore_project.py; no network or external files required')
    save('PACKAGE_MANIFEST.json',manifest)
    building=ARCHIVE.with_suffix('.building.zip')
    with zipfile.ZipFile(building,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(direct+[ROOT/'PACKAGE_MANIFEST.json']):
            method=zipfile.ZIP_STORED if p.suffix in {'.zip','.xz'} else zipfile.ZIP_DEFLATED
            z.write(p,ROOT.name+'/'+str(p.relative_to(ROOT)),compress_type=method)
    with zipfile.ZipFile(building) as z:
        assert z.testzip() is None and len(z.infolist())==len(records)+1
        for n,r in records.items():
            b=z.read(ROOT.name+'/'+n);assert len(b)==r['bytes'] and sha(b)==r['sha256'],n
        assert json.loads(z.read(ROOT.name+'/PACKAGE_MANIFEST.json'))==manifest
        with tarfile.open(fileobj=io.BytesIO(z.read(ROOT.name+'/EXPERIMENT_DATA.tar.xz')),mode='r:xz') as tar:
            assert len(tar.getmembers())==len(data_records)
            for m in tar.getmembers():
                assert m.isfile() and m.name in data_records
                b=tar.extractfile(m).read();r=data_records[m.name]
                assert len(b)==r['bytes'] and sha(b)==r['sha256'],m.name
    building.replace(ARCHIVE)
    outcome=dict(path=str(ARCHIVE),bytes=ARCHIVE.stat().st_size,sha256=sha(ARCHIVE.read_bytes()),
                 direct_entries=len(records)+1,inherited_files=len(inherited),packed_data_files=len(data),
                 all_entries_read_back_verified=True)
    (ROOT.parent/'QKF_RESULT_OBSERVATIONS_2026-09-13.archive.json').write_text(json.dumps(outcome,indent=2)+'\n')
    print(json.dumps(outcome,indent=2))
