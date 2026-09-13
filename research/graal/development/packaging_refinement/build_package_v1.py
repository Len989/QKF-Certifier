"""Build a complete handoff, preserving the exact preceding archive."""
import argparse, hashlib, json, lzma, tarfile, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent
PREFIX = 'qkf_universal_lower_2026-09-13/'
PRIOR_NAME = 'QKF_UNIVERSAL_UPPER_2026-09-13.zip'
PRIOR_HASH = '8dab8d38e8d1fc7a6b7715c258cd45dfbb281331d041afb977195c9c8835c592'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metadata(path):
    return dict(bytes=path.stat().st_size, sha256=sha(path))


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--prior', type=Path, default=ROOT.parent / PRIOR_NAME)
    p.add_argument('--output', type=Path, default=ROOT.parent / 'QKF_UNIVERSAL_LOWER_2026-09-13.zip')
    a = p.parse_args()
    if a.output.exists():
        raise SystemExit('Refusing to replace an existing package: ' + str(a.output))
    if sha(a.prior) != PRIOR_HASH:
        raise ValueError('Exact previous archive required')
    from audit_step import audit
    if audit()['status'] != 'passed':
        raise ValueError('Evidence audit failed')
    excluded = {'__pycache__', 'papers', 'prior_stage', 'reproduction'}
    paths = [p for p in sorted(ROOT.rglob('*')) if p.is_file() and p.parent != ROOT
             and not set(p.relative_to(ROOT).parts) & excluded and p.suffix not in {'.pyc', '.tmp'}]
    if any(p.is_symlink() for p in paths):
        raise ValueError('Package must contain regular project files')
    records = {str(p.relative_to(ROOT)):metadata(p) for p in paths}
    packed = ROOT / 'EXPERIMENT_DATA.tar.xz'; manifest = ROOT / 'DATA_MANIFEST.json'
    old = json.loads(manifest.read_text()) if manifest.exists() else None
    if not (old and old['files'] == records and packed.exists() and old['archive_sha256'] == sha(packed)):
        temp = packed.with_suffix('.xz.tmp')
        with tarfile.open(temp, 'w:xz', preset=9 | lzma.PRESET_EXTREME) as tar:
            for path in paths:
                info = tar.gettarinfo(str(path), arcname=str(path.relative_to(ROOT)))
                info.uid = info.gid = 0; info.uname = info.gname = ''; info.mtime = 0; info.mode = 0o644
                with path.open('rb') as f:
                    tar.addfile(info, f)
        temp.replace(packed)
        save(manifest, dict(schema='qkf-universal-lower-packed-data-v1', archive=packed.name,
                            archive_sha256=sha(packed), files=records))
    direct = [p for p in sorted(ROOT.iterdir()) if p.is_file() and p.suffix in {'.md','.py','.json'}
              and p.name != 'PACKAGE_MANIFEST.json']
    package_records = {p.name:metadata(p) for p in direct}
    package_records[packed.name] = metadata(packed)
    prior_member = 'prior_stage/' + PRIOR_NAME; package_records[prior_member] = metadata(a.prior)
    save(ROOT / 'PACKAGE_MANIFEST.json', dict(schema='qkf-universal-lower-complete-package-v1', files=package_records,
        packed_files=len(records), inherited_paper_files=len(json.loads((ROOT / 'PAPERS_INHERITANCE.json').read_text())['files']),
        history='Exact complete previous archive plus its complete earlier archives; papers recovered through the fully verified nested archive chain',
        optional_dependencies='Pinned JVM/ECJ metadata retained; installed binaries and a new solver are not required for proof replay'))
    with zipfile.ZipFile(a.output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in direct + [ROOT / 'PACKAGE_MANIFEST.json']:
            z.write(path, PREFIX + path.name)
        z.write(packed, PREFIX + packed.name, compress_type=zipfile.ZIP_STORED)
        z.write(a.prior, PREFIX + prior_member, compress_type=zipfile.ZIP_STORED)
    with zipfile.ZipFile(a.output) as z:
        if z.testzip() is not None or set(z.namelist()) != {PREFIX+n for n in package_records} | {PREFIX+'PACKAGE_MANIFEST.json'}:
            raise ValueError('Package membership or CRC')
        for name, r in package_records.items():
            data = z.read(PREFIX + name)
            if len(data) != r['bytes'] or hashlib.sha256(data).hexdigest() != r['sha256']:
                raise ValueError('Package member checksum: ' + name)
    print(json.dumps(dict(status='built_and_verified', path=str(a.output), bytes=a.output.stat().st_size,
                         sha256=sha(a.output), packed_files=len(records), packed_bytes=packed.stat().st_size,
                         below_50_mib=a.output.stat().st_size < 50 * 1024**2)))
