"""Additional PR36-byte protection; only registry and current workflow may change."""
import hashlib
import json
from pathlib import Path
import subprocess

BASE='27e9a7c456c928694eee808a8a6c59967b13bc9a'
EDITABLE={'.github/workflows/current-research.yml','research/regression/SUITES.json'}

def audit():
    inventory={}
    for item in subprocess.check_output(['git','ls-tree','-rz',BASE]).split(b'\0'):
        if not item:continue
        meta,name=item.split(b'\t');mode,kind,expected=meta.decode().split();name=name.decode()
        if name in EDITABLE:continue
        p=Path(name);raw=p.read_bytes();actual=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        current='100755' if p.stat().st_mode&0o111 else '100644'
        if p.is_symlink() or kind!='blob' or current!=mode or actual!=expected:raise ValueError('accepted path changed: '+name)
        inventory[name]={'sha256':hashlib.sha256(raw).hexdigest(),'mode':mode}
    return {'base_tree':BASE,'preserved_files':len(inventory),'edit_exceptions':sorted(EDITABLE),
            'inventory_sha256':hashlib.sha256(json.dumps(inventory,sort_keys=True).encode()).hexdigest()}

if __name__=='__main__':print(json.dumps(audit(),sort_keys=True))
