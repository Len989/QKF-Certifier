from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'public_runtime/src'),str(ROOT/'public_runtime/tests'),str(ROOT/'legacy'),
              str(ROOT/'legacy/frozen_qkf'),str(ROOT/'legacy/frozen_qkf/dependencies'),str(ROOT/'symbolic/core'),str(ROOT/'symbolic')]

def save(path,obj):
 import json
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(obj,indent=2)+'\n');t.replace(p)
