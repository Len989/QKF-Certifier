"""Serialize existing QKF data as Lean constants; never writes a proof tactic.

The resulting constants are untrusted input to a separately written Lean
checker and generic soundness theorem. Original evidence remains intact.
"""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def export(source):
    whole=json.loads(source.read_text());c=whole['successor']
    if c['schema']!='qkf-lower-carry-closure-v1':raise ValueError('certificate schema')
    if len(c['states'])!=8 or len(c['rows'])!=8 or c['initial']!=0:raise ValueError('pilot dimensions')
    if len(c['edges'])!=8 or any(len(row)!=6 for row in c['edges']):raise ValueError('complete transition matrix')
    if any(type(j) is not int or not 0<=j<8 for row in c['edges'] for j in row):raise ValueError('edge range')
    relation={-1:'.lt',0:'.eq',1:'.gt'}
    def boolean(x):
        if type(x) not in {bool,int} or x not in (0,1):raise ValueError('Boolean data')
        return 'true' if x else 'false'
    def obs(q):
        if len(q)!=7 or any(type(v) is not int or v not in relation for v in q[1:4]):raise ValueError('observation')
        return '⟨'+', '.join([boolean(q[0])]+[relation[v] for v in q[1:4]]+[boolean(b) for b in q[4:]])+'⟩'
    lines=['import QKF.Core','','/- Generated data only. Checked.lean supplies the proof. -/','namespace QKF.Data','',
           'def states (i : Fin 8) : Observation :=','  match i.val with']
    for i,q in enumerate(c['states']):lines.append(f'  | {i if i<7 else "_"} => {obs(q)}')
    lines+=['','def edges (i : Fin 8) (c : Column) : Fin 8 :=','  match i.val, c.val with']
    for i,row in enumerate(c['edges']):
        for j,v in enumerate(row):lines.append(f'  | {i}, {j} => {v}')
    lines+=['  | _, _ => 0','','def rows (r : Fin 8) (p : Fin 4) : Fin 4 :=','  match r.val, p.val with']
    for i,r in enumerate(c['rows']):
        if len(r['table'])!=4 or any(type(v) is not int or not 0<=v<4 for v in r['table']):raise ValueError('row table')
        for j,v in enumerate(r['table']):lines.append(f'  | {i}, {j} => {v}')
    lines+=['  | _, _ => 0','','end QKF.Data','']
    return '\n'.join(lines)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,default=ROOT/'evidence/lower_certificate.json');p.add_argument('--output',type=Path,default=ROOT/'QKF/Data.lean');p.add_argument('--check',action='store_true');a=p.parse_args()
    content=export(a.input)
    if a.check:
        if a.output.read_text()!=content:raise SystemExit('Generated constants differ from the retained certificate')
    else:a.output.write_text(content)
    print(json.dumps(dict(status='matched' if a.check else 'exported',source_sha256=hashlib.sha256(a.input.read_bytes()).hexdigest(),lean_sha256=hashlib.sha256(content.encode()).hexdigest(),states=8,edges=48,rows=8)))
