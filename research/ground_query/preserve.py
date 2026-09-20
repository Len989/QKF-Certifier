"""Audit accepted PR39 bytes and exact provenance of the namespaced prototype."""

import hashlib
import json
from pathlib import Path
import subprocess

BASE = 'a92caf36c0b6567bfe509dfda344c12c73314b1a'
EDITABLE = {'.github/workflows/current-research.yml', 'research/regression/SUITES.json'}


def provenance():
    meta = json.loads(Path('research/ground_query/prototype/PROVENANCE.json').read_text())
    for item in meta['files']:
        raw = Path(item['source']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item['source_sha256']:
            raise ValueError('retained prototype changed')
        text = raw.decode()
        if 'extraction' in item:
            spec = item['extraction']
            text = spec['header'] + text[text.index(spec['start']):text.index(spec['end'])] + spec['suffix']
        else:
            for edit in item['replacements']:
                text = text.replace(edit['old'], edit['new'])
        actual = Path(item['target']).read_bytes()
        if actual != text.encode() or hashlib.sha256(actual).hexdigest() != item['target_sha256']:
            raise ValueError('unregistered prototype adaptation')
    return len(meta['files'])


def audit():
    inventory = {}
    for item in subprocess.check_output(['git', 'ls-tree', '-rz', BASE]).split(b'\0'):
        if not item:
            continue
        meta, raw_name = item.split(b'\t', 1)
        mode, kind, expected = meta.decode().split()
        name = raw_name.decode()
        if name in EDITABLE:
            continue
        path = Path(name)
        raw = path.read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        actual_mode = '100755' if path.stat().st_mode & 0o111 else '100644'
        if path.is_symlink() or kind != 'blob' or mode != actual_mode or expected != actual:
            raise ValueError('accepted file changed: ' + name)
        inventory[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'mode': mode}
    return {'base': BASE, 'preserved_files': len(inventory), 'prototype_adaptations': provenance(),
            'inventory_sha256': hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()}


if __name__ == '__main__':
    print(json.dumps(audit(), sort_keys=True))
