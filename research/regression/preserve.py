"""Protect accepted PR35 bytes; permit additive current-tree development.

This is NOT an exact-new-file-set freeze. New PRs update SUITES.json and may add
modules without archiving this harness. Intentional edits to accepted source
require an explicit reviewed policy change. Historical experiment locks remain
checked in their own pinned exports; they are not rewritten by this audit.
"""
import hashlib
import json
from pathlib import Path
import subprocess

BASE='c02e5ac45473da2ce1f3772dee11246297737a2f'
EDITABLE={'.github/workflows/signed-guarded-coverage.yml'}


def audit():
    inventory={};old=set()
    for item in subprocess.check_output(['git','ls-tree','-rz',BASE]).split(b'\0'):
        if not item:continue
        meta,raw_name=item.split(b'\t',1);mode,kind,expected=meta.decode().split();name=raw_name.decode()
        old.add(name)
        if name in EDITABLE:continue
        path=Path(name);raw=path.read_bytes()
        actual=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        actual_mode='100755' if path.stat().st_mode & 0o111 else '100644'
        if kind!='blob' or path.is_symlink() or expected!=actual or mode!=actual_mode:
            raise ValueError('accepted file changed: '+name)
        inventory[name]={'sha256':hashlib.sha256(raw).hexdigest(),'mode':mode}
    current=set(subprocess.check_output(['git','ls-files','-z']).decode().split('\0'))-{''}
    if not old <= current:raise ValueError('accepted tracked file removed')
    return {'base_tree':BASE,'preserved_files':len(inventory),'explicit_edit_exceptions':sorted(EDITABLE),
            'additive_paths':sorted(current-old),'inventory_sha256':hashlib.sha256(
                json.dumps(inventory,sort_keys=True).encode()).hexdigest()}


if __name__=='__main__':print(json.dumps(audit(),sort_keys=True))
