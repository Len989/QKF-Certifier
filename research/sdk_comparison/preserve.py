"""Preserve all accepted PR46 bytes except current CI wiring and additive registry."""
import hashlib
import json
from pathlib import Path
import subprocess

BASE = '925cf42c83b4e676b20ed18fc301ebb505753c3a'
EDITABLE = {'.github/workflows/current-research.yml', 'research/regression/SUITES.json'}


def audit():
    inventory = {}
    for row in subprocess.check_output(['git', 'ls-tree', '-rz', BASE]).split(b'\0'):
        if not row:
            continue
        meta, raw = row.split(b'\t', 1)
        mode, kind, expected = meta.decode().split()
        name = raw.decode()
        if name in EDITABLE:
            continue
        p = Path(name)
        data = p.read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        actual_mode = '100755' if p.stat().st_mode & 0o111 else '100644'
        if p.is_symlink() or kind != 'blob' or mode != actual_mode or actual != expected:
            raise ValueError('accepted PR46 file changed: ' + name)
        inventory[name] = dict(sha256=hashlib.sha256(data).hexdigest(), mode=mode)
    return dict(base=BASE, preserved_files=len(inventory), inventory_sha256=hashlib.sha256(
        json.dumps(inventory, sort_keys=True).encode()).hexdigest())


if __name__ == '__main__':
    print(json.dumps(audit(), sort_keys=True))
