"""Preserve accepted PR40 bytes; only the existing CI and registry may change."""
import hashlib
import json
from pathlib import Path
import subprocess

BASE = '422891e21d453a6694d924d86f243431bae8ae33'
EDITABLE = {'.github/workflows/current-research.yml', 'research/regression/SUITES.json'}


def audit():
    inventory = {}
    for row in subprocess.check_output(['git', 'ls-tree', '-rz', BASE]).split(b'\0'):
        if not row:
            continue
        meta, raw_name = row.split(b'\t', 1)
        mode, kind, expected = meta.decode().split()
        name = raw_name.decode()
        if name in EDITABLE:
            continue
        p = Path(name)
        raw = p.read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        actual_mode = '100755' if p.stat().st_mode & 0o111 else '100644'
        if p.is_symlink() or kind != 'blob' or mode != actual_mode or actual != expected:
            raise ValueError('accepted file changed: ' + name)
        inventory[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'mode': mode}
    return {'base': BASE, 'preserved_files': len(inventory),
            'inventory_sha256': hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()}


if __name__ == '__main__':
    print(json.dumps(audit(), sort_keys=True))
