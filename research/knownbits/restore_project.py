"""Restore exact inherited sources and packed evidence using only the stdlib.

No network, no external history and no overwrite of differing local files.
The complete prior archive remains intact inside this package.
"""
import hashlib,json,stat,tarfile,zipfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parent
PRIOR_HASH='4d2d70618c7fc663569b9b44fbfba280e020268119e70e6695c29f796f1622fa'


def sha(data):return hashlib.sha256(data).hexdigest()


def destination(name):
    n=PurePosixPath(name)
    if n.is_absolute() or '..' in n.parts or str(n)!=name or '\\' in name:
        raise ValueError('unsafe member path: '+name)
    p=ROOT.joinpath(*n.parts)
    if p.is_symlink() or not p.resolve().is_relative_to(ROOT):
        raise ValueError('unsafe existing path: '+name)
    return p


def validate(data,r,name):
    if len(data)!=r['bytes'] or sha(data)!=r['sha256']:
        raise ValueError('checksum mismatch: '+name)


def write_missing(name,data,r):
    validate(data,r,name);p=destination(name)
    if p.exists():
        if not p.is_file() or p.read_bytes()!=data:
            raise ValueError('existing file differs; refusing overwrite: '+name)
        return 0
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(data)
    return 1


def restore():
    inherited=json.loads((ROOT/'INHERITED_FILES.json').read_text())
    packed=json.loads((ROOT/'DATA_MANIFEST.json').read_text())
    # Reject a local conflict before restoring any missing data.
    for n,r in {**inherited['files'],**packed['files']}.items():
        p=destination(n)
        if p.exists():
            if not p.is_file():raise ValueError('non-file destination: '+n)
            validate(p.read_bytes(),r,n)
    prior=destination(inherited['archive'])
    if inherited['archive_sha256']!=PRIOR_HASH or sha(prior.read_bytes())!=PRIOR_HASH:
        raise ValueError('exact prior archive checksum')
    created_sources=0
    with zipfile.ZipFile(prior) as z:
        for n,r in inherited['files'].items():
            m=z.getinfo(r['member'])
            if m.is_dir() or stat.S_ISLNK(m.external_attr>>16):raise ValueError('invalid inherited member')
            created_sources+=write_missing(n,z.read(m),r)
    archive=destination(packed['archive'])
    if sha(archive.read_bytes())!=packed['archive_sha256']:raise ValueError('packed data checksum')
    created_data=0
    with tarfile.open(archive,'r:xz') as tar:
        members=tar.getmembers()
        if len(members)!=len(packed['files']) or {m.name for m in members}!=set(packed['files']):
            raise ValueError('packed membership')
        for m in members:
            destination(m.name)
            if not m.isfile():raise ValueError('invalid data member')
        for m in members:
            created_data+=write_missing(m.name,tar.extractfile(m).read(),packed['files'][m.name])
    return dict(status='restored' if created_sources+created_data else 'already_present',
                inherited_files=len(inherited['files']),data_files=len(packed['files']),
                created_sources=created_sources,created_data=created_data)


if __name__=='__main__':print(json.dumps(restore()))
