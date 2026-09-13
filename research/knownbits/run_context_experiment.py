"""Serial three-arm corpus run followed by fixed mechanism tests."""
import json,subprocess,sys
from environment import ROOT,save
from freeze_context import verify


if __name__=='__main__':
    print(verify(),flush=True)
    for mode in ['baseline','guards','context']:
        log=ROOT/'results'/mode/'run.log';log.parent.mkdir(parents=True,exist_ok=True)
        print('START',mode,flush=True)
        with log.open('x') as f:
            subprocess.run([sys.executable,str(ROOT/'context_run.py'),'--mode',mode,'--output',str(log.parent)],stdout=f,stderr=subprocess.STDOUT,check=True)
        data=json.loads((log.parent/'summary.json').read_text())
        print('COMPLETE',mode,'programs',len(data['records']),flush=True)
    for script,args in [('validate_context.py',['--suite','representations','--output','validation/frozen_representations']),
                        ('validate_consumers.py',['--output','validation/frozen_consumers'])]:
        subprocess.run([sys.executable,str(ROOT/script),*args],check=True)
    print('UNCHANGED',verify(),flush=True)
