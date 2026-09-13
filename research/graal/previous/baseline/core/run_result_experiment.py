"""Serial frozen comparison; no concurrent benchmark workers."""
import json,subprocess,sys
from environment import ROOT
from freeze_result import verify


if __name__=='__main__':
    print(verify(),flush=True)
    for mode in ['baseline','sign','observed']:
        log=ROOT/'results'/mode/'run.log';log.parent.mkdir(parents=True,exist_ok=True)
        print('START',mode,flush=True)
        with log.open('x') as f:
            subprocess.run([sys.executable,str(ROOT/'result_run.py'),'--mode',mode,'--output',str(log.parent)],
                           stdout=f,stderr=subprocess.STDOUT,check=True)
        records=json.loads((log.parent/'summary.json').read_text())['records']
        print('COMPLETE',mode,'programs',len(records),'whole',sum(r['producer']['status']=='certificate_produced' for r in records),flush=True)
    subprocess.run([sys.executable,str(ROOT/'validate_result.py'),'--output','validation/frozen'],check=True)
    print('UNCHANGED',verify(),flush=True)
