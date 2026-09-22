"""Preserve the accepted PR48 engine, with explicit live CI exceptions.

The old PR48 gate still describes its original tree exactly. This new gate is
used for current-tree runs after the documented historical-workflow changes.
It does not edit or monkeypatch any older preservation code or registration.
"""
import hashlib
import json
from pathlib import Path
import subprocess

BASE = '417f603eb2dd7e70c108d1f911ab4593e6a6ea58'
EDITABLE = {'research/regression/SUITES.json', '.github/workflows/sdk-cost-contracts.yml',
            '.github/workflows/prepared-context.yml'}


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
            raise ValueError('accepted PR48 file changed: ' + name)
        inventory[name] = dict(sha256=hashlib.sha256(data).hexdigest(), mode=mode)
    # The registry is additive even though new/prior grouping can change.
    old = json.loads(subprocess.check_output(['git', 'show', BASE + ':research/regression/SUITES.json']))
    now = json.loads(Path('research/regression/SUITES.json').read_text())
    if not set(old['new'] + old['prior']) <= set(now['new'] + now['prior']):
        raise ValueError('accepted regression suite removed')
    return dict(base=BASE, preserved_files=len(inventory), explicit_edit_exceptions=sorted(EDITABLE),
                inventory_sha256=hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest())


if __name__ == '__main__':
    print(json.dumps(audit(), sort_keys=True))
