"""Produce finite rows and a closed joint observation carrier; never imported by replay."""
from carry_kernel import *

def produce(program):
    bridge,cells=source_quotient(program);proofs=[]
    for label in labels():
        supplied=[[1,atom(cells,label,0)],[2,atom(cells,label,1)]];values=dict(supplied);steps=[]
        for op in ['intersection','union']:
            src=0 if op=='intersection' else 3;dst=values[1]&values[2] if op=='intersection' else values[1]|values[2]
            steps.append(dict(operation=op,left=1,right=2,input=src,output=dst));values[src]=dst
        table=[values[i] for i in range(4)]
        proofs.append(dict(label=list(label),supplied=supplied,steps=steps,table=table,kernel=[[i for i in range(4) if table[i]==v] for v in sorted(set(table))]))
    rows=replay_rows(program,bridge,proofs);states=[START];indices={START:0};edges=[];ends=[]
    for q in states:
        end=boundaries(q)
        if any(e['bad'] for e in end):return dict(status='counterexample',state=list(q),boundaries=end)
        ends.append(end);row=[]
        for col in ALPHABET:
            t=transition(q,col,rows)
            if t not in indices:indices[t]=len(states);states.append(t)
            row.append(indices[t])
        edges.append(row)
    c=dict(schema=SCHEMA,program=program,source_quotient=bridge,rows=proofs,states=[list(q) for q in states],initial=0,edges=edges,boundaries=ends,conclusion=CONCLUSION)
    return dict(status='certificate_produced',certificate=c,replay=replay(program,c))
