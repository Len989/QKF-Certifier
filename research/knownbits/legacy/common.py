from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'baseline'
def setup(repo):
    repo=Path(repo).resolve()
    sys.path[:0]=[str(repo/'src'),str(repo/'tests'),str(ROOT),str(BASE/'frozen_qkf'),str(BASE/'frozen_qkf/dependencies')]
    return repo
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)
def check_baseline(repo):
    meta=json.loads((BASE/'FREEZE.json').read_text())
    for key,where in [('frozen_research_python_sha256',BASE/'frozen_qkf'),('frozen_public_python_sha256',repo)]:
        for n,h in meta[key].items():
            if hashlib.sha256((where/n).read_bytes()).hexdigest()!=h:raise ValueError('baseline changed: '+n)
    st=json.loads((ROOT/'STAGE.json').read_text())
    for n,h in st['input_sha256'].items():
        if hashlib.sha256((BASE/'cases'/n).read_bytes()).hexdigest()!=h:raise ValueError('source changed: '+n)
    return {'unchanged_baseline_python_files':23,'unchanged_llvm_inputs':11}
