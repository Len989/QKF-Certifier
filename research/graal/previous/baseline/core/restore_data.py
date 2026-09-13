"""Restore the losslessly packed experiment data; verify every member first.

Source code and papers are directly in the ZIP. Only bulky result JSON and
development evidence use a solid tar.xz container to avoid repeated copies.
"""
import hashlib,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent


def restore():
    manifest=json.loads((ROOT/'DATA_MANIFEST.json').read_text())
    expected=manifest['files'];missing=[]
    for n,r in expected.items():
        p=ROOT/n
        if p.exists():
            if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=r['sha256']:
                raise ValueError('existing data differs; refusing overwrite: '+n)
        else:missing.append(n)
    if not missing:return dict(status='already_present',files=len(expected))
    archive=ROOT/'EXPERIMENT_DATA.tar.xz'
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=manifest['archive_sha256']:
        raise ValueError('packed data checksum')
    with tarfile.open(archive,'r:xz') as tar:
        members=tar.getmembers()
        if len(members)!=len(expected) or {m.name for m in members}!=set(expected):
            raise ValueError('packed data membership')
        for m in members:
            p=ROOT/m.name
            if not m.isfile() or p.resolve().is_relative_to(ROOT.resolve()) is False:
                raise ValueError('invalid data member')
            data=tar.extractfile(m).read();r=expected[m.name]
            if len(data)!=r['bytes'] or hashlib.sha256(data).hexdigest()!=r['sha256']:
                raise ValueError('data member checksum: '+m.name)
            if m.name in missing:
                p.parent.mkdir(parents=True,exist_ok=True)
                with p.open('xb') as f:f.write(data)
    return dict(status='restored',files=len(expected),created=len(missing))


if __name__=='__main__':print(json.dumps(restore()))
