"""Check the accepted PR45 tree without weakening any earlier preservation gate."""
import hashlib
import json
from pathlib import Path
import subprocess

BASE = 'b7e500bf5636b59b2f04f309d7fbddc83cd40186'
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
        path = Path(name)
        data = path.read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        actual_mode = '100755' if path.stat().st_mode & 0o111 else '100644'
        if path.is_symlink() or kind != 'blob' or actual_mode != mode or actual != expected:
            raise ValueError('accepted PR45 file changed: ' + name)
        inventory[name] = dict(sha256=hashlib.sha256(data).hexdigest(), mode=mode)
    return dict(base=BASE, preserved_files=len(inventory),
                inventory_sha256=hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest())


if __name__ == '__main__':
    print(json.dumps(audit(), sort_keys=True))
