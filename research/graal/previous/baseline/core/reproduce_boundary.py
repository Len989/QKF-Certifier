"""Repeat both frozen revisions in a fresh directory, preserving reference data."""
import datetime,json,shutil,subprocess,sys
from pathlib import Path
from freeze_boundary import verify
ROOT=Path(__file__).resolve().parent


if __name__=='__main__':
    print('Verified v1 mechanism:',verify(),flush=True)
    frozen=json.loads((ROOT/'FREEZE_V2.json').read_text())['files']
    dest=ROOT/'reproduction'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    dest.mkdir(parents=True,exist_ok=False)
    for name in list(frozen)+['FREEZE_V2.json','audit_boundary.py']:
        target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    print('Fresh experiment:',dest,flush=True)
    steps=[('v1_representations',['boundary_representation_run.py'])]+[
        ('v1_'+m,['boundary_run.py','--mode',m,'--output','results/'+m]) for m in ['previous','endpoints','boundary']]+[
        ('v2_representations',['boundary_v2_representation_run.py'])]+[
        ('v2_'+m,['boundary_v2_run.py','--mode',m,'--output','results_v2/'+m]) for m in ['endpoints','boundary']]
    logs=dest/'reproduction_logs';logs.mkdir()
    for name,command in steps:
        print('Running',name,flush=True)
        with (logs/(name+'.log')).open('x') as f:
            result=subprocess.run([sys.executable,*command],cwd=dest,stdout=f,stderr=subprocess.STDOUT)
        if result.returncode:raise SystemExit(result.returncode)
    # Repeated timings and telemetry differ; all certificate/source hashes
    # inside the new results are still verified. The original snapshot remains.
    subprocess.run([sys.executable,'audit_boundary.py','--fresh-results'],cwd=dest,check=True)
    print('Reproduction completed:',dest,flush=True)
