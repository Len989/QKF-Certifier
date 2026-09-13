"""Reproduce in an isolated directory; never overwrite the recorded experiment."""
import datetime,json,shutil,subprocess,sys
from pathlib import Path
from environment import ROOT
from freeze_context import verify


if __name__=='__main__':
    verify();f=json.loads((ROOT/'FREEZE.json').read_text())
    dst=ROOT/'reproduction'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    dst.mkdir(parents=True)
    for name in list(f['files'])+['FREEZE.json','audit_context.py']:
        p=dst/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,p)
    prior='prior_stage/QKF_BOUNDARY_ACTIONS_2026-09-13.zip'
    (dst/'prior_stage').mkdir();shutil.copy2(ROOT/prior,dst/prior)
    subprocess.run([sys.executable,str(dst/'run_context_experiment.py')],cwd=dst,check=True)
    subprocess.run([sys.executable,str(dst/'audit_context.py')],cwd=dst,check=True)
    print(dst)
