"""Full exported Git-tree reconstruction. No historical freeze exclusions."""
import hashlib
from pathlib import Path
import stat


def snapshot(root):
    inventory={}
    def obj(kind,raw):
        return hashlib.sha1(kind+b' '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    def walk(folder,relative=''):
        entries=[]
        for path in folder.iterdir():
            if path.name=='__pycache__' or path.name.endswith(('.pyc','.pyo')): continue
            rel=relative+path.name; mode=path.lstat().st_mode
            if stat.S_ISLNK(mode): raise ValueError('symlink: '+rel)
            if stat.S_ISDIR(mode):
                entries.append((path.name+'/',b'40000',path.name,walk(path,rel+'/')))
            elif stat.S_ISREG(mode):
                raw=path.read_bytes(); gitmode=b'100755' if mode&0o111 else b'100644'
                inventory[rel]={'sha256':hashlib.sha256(raw).hexdigest(),'mode':gitmode.decode(),'bytes':len(raw)}
                entries.append((path.name,gitmode,path.name,obj(b'blob',raw)))
            else: raise ValueError('nonregular: '+rel)
        raw=b''.join(m+b' '+n.encode()+b'\0'+bytes.fromhex(h) for _,m,n,h in
                     sorted(entries,key=lambda e:e[0].encode()))
        return obj(b'tree',raw)
    tree=walk(Path(root))
    return {'tree':tree,'count':len(inventory),'files':dict(sorted(inventory.items()))}
