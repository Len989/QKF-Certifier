"""Lossless local restore of current evidence and both papers from exact history."""
import hashlib, io, json, stat, tarfile, zipfile
from pathlib import Path, PurePosixPath
ROOT = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe(name):
    n = PurePosixPath(name)
    if n.is_absolute() or '..' in n.parts or str(n) != name or '\\' in name:
        raise ValueError('Unsafe path: ' + name)
    p = ROOT.joinpath(*n.parts)
    if p.is_symlink() or not p.resolve().is_relative_to(ROOT):
        raise ValueError('Unsafe destination: ' + name)
    return p


def validate(data, record, name):
    if len(data) != record['bytes'] or sha(data) != record['sha256']:
        raise ValueError('Checksum: ' + name)


def check_existing(name, record):
    p = safe(name)
    if p.exists():
        if not p.is_file():
            raise ValueError('Not a file: ' + name)
        validate(p.read_bytes(), record, name)


def put(name, data, record):
    validate(data, record, name); p = safe(name)
    if p.exists():
        if not p.is_file() or p.read_bytes() != data:
            raise ValueError('Refusing overwrite: ' + name)
        return 0
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as f:
        f.write(data)
    return 1


def zip_member(z, name):
    if z.namelist().count(name) != 1:
        raise ValueError('Missing/duplicated inherited member: ' + name)
    member = z.getinfo(name)
    mode = stat.S_IFMT(member.external_attr >> 16)
    if member.is_dir() or mode not in {0, stat.S_IFREG}:
        raise ValueError('Nonregular inherited member: ' + name)
    return z.read(member)


def restore():
    package = json.loads((ROOT / 'PACKAGE_MANIFEST.json').read_text())
    for name, r in package['files'].items():
        p = safe(name)
        if not p.is_file():
            raise ValueError('Missing direct package member: ' + name)
        validate(p.read_bytes(), r, name)
    packed = json.loads((ROOT / 'DATA_MANIFEST.json').read_text())
    inherited = json.loads((ROOT / 'PAPERS_INHERITANCE.json').read_text())
    if set(packed['files']) & set(inherited['files']):
        raise ValueError('Ambiguous restored membership')
    for name, r in {**packed['files'], **inherited['files']}.items():
        check_existing(name, r)
    archive = safe(packed['archive'])
    if sha(archive.read_bytes()) != packed['archive_sha256']:
        raise ValueError('Packed evidence checksum')
    restored_data = 0
    with tarfile.open(archive, 'r:xz') as tar:
        members = tar.getmembers()
        if len(members) != len(packed['files']) or {m.name for m in members} != set(packed['files']):
            raise ValueError('Packed membership')
        for m in members:
            safe(m.name)
            if not m.isfile() or m.size != packed['files'][m.name]['bytes']:
                raise ValueError('Invalid packed member')
        for m in members:
            restored_data += put(m.name, tar.extractfile(m).read(), packed['files'][m.name])
    data = safe(inherited['archive']).read_bytes()
    if sha(data) != inherited['archive_sha256']:
        raise ValueError('Exact previous archive checksum')
    for entry in inherited['chain']:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            data = zip_member(z, entry['member'])
        if sha(data) != entry['sha256']:
            raise ValueError('Nested history checksum: ' + entry['member'])
    restored_papers = 0
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name, r in inherited['files'].items():
            restored_papers += put(name, zip_member(z, r['member']), r)
    return dict(status='restored' if restored_data + restored_papers else 'already_present',
                data_files=len(packed['files']), paper_files=len(inherited['files']),
                restored_data=restored_data, restored_papers=restored_papers,
                prior_archive='Complete exact previous archive retained',
                history_chain_archives=1 + len(inherited['chain']))


if __name__ == '__main__':
    print(json.dumps(restore()))
