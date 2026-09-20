"""Current-tree harness audit, distinct from the two exact solver exports."""
import hashlib
import json
from pathlib import Path
import subprocess

BASE='4c1dfe4047c7bc44ca45e0dc3e73b37517859dda'
HARNESS='.github/workflows/signed-row-targets.yml'


def main():
    old=set(); inventory={}
    entries=subprocess.check_output(['git','ls-tree','-rz',BASE])
    for entry in filter(None,entries.split(b'\0')):
        meta,name=entry.split(b'\t',1); mode,kind,expected=meta.decode().split(); name=name.decode();old.add(name)
        if name==HARNESS: continue
        p=Path(name);raw=p.read_bytes()
        actual=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        actual_mode='100755' if p.stat().st_mode&0o111 else '100644'
        if p.is_symlink() or kind!='blob' or expected!=actual or mode!=actual_mode:
            raise ValueError('accepted file changed: '+name)
        inventory[name]=hashlib.sha256(raw).hexdigest()
    current=set(subprocess.check_output(['git','ls-files','-z']).decode().split('\0'))-{''}
    added=current-old
    allowed_docs={'docs/CLAIMS_POST_PR31_RU.md','docs/QKF_ROADMAP_v0.2_RU.md',
                  'docs/PAPER_III_POST_PR31_ADDENDUM_RU.md'}
    if not old<=current or any(not (n.startswith('research/acceptance/') or n in allowed_docs
                                    or n=='.github/workflows/block-a-acceptance.yml') for n in added):
        raise ValueError('unexpected added/deleted path')
    print(json.dumps({'base_tree':BASE,'preserved_files':len(inventory),'changed_live_harness':HARNESS,
                      'added_files':sorted(added),'inventory_sha256':hashlib.sha256(
                          json.dumps(inventory,sort_keys=True).encode()).hexdigest()},sort_keys=True))


if __name__=='__main__': main()
