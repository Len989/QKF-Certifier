"""Find a finite closed carrier and export explicit row and induction evidence."""
from collections import deque
from row_kernel import atom,labels,replay_rows
from sweep_kernel import START,ALPHABET,SCHEMA,transition,boundary,replay


def produce_rows(guard):
    records=[]
    for label in labels():
        supplied=[[1<<(r+1),atom(guard,label,r)] for r in (-1,0,1)]
        values=dict(supplied);steps=[]
        for op,a,b in [('intersection',1,2),('union',1,2),('union',1,4),('union',2,4),('union',3,4)]:
            src=a|b if op=='union' else a&b;dst=values[a]|values[b] if op=='union' else values[a]&values[b]
            steps.append(dict(operation=op,left=a,right=b,input=src,output=dst));values[src]=dst
        table=[values[i] for i in range(8)]
        records.append(dict(label=list(label),supplied=supplied,steps=steps,table=table,
                            kernel=[[i for i in range(8) if table[i]==v] for v in sorted(set(table))]))
    return records


def produce(guard):
    row_certificates=produce_rows(guard);rows=replay_rows(guard,row_certificates)
    states=[START];indices={START:0};parents={START:None};edges=[];boundaries=[]
    for q in states:
        ends=[boundary(q,a,u) for a in (0,1) for u in (0,1)]
        if any(x['bad'] for x in ends):
            sign_index=next(i for i,x in enumerate(ends) if x['bad']);path=[];p=q
            while parents[p] is not None:
                p,col=parents[p];path.append(col)
            path.reverse();a,u=divmod(sign_index,2);path.append((a,0,u,a,a))
            return dict(status='counterexample',width=len(path),columns=path,
                        words=dict(zip(['base','optional','bound','candidate','output'],
                                       [sum(c[i]<<j for j,c in enumerate(path)) for i in range(5)])))
        boundaries.append(ends);row=[]
        for col in ALPHABET:
            r=transition(q,col,rows)
            if r not in indices:
                indices[r]=len(states);states.append(r);parents[r]=(q,col)
            row.append(indices[r])
        edges.append(row)
    c=dict(schema=SCHEMA,guard=guard,rows=row_certificates,states=[list(q) for q in states],initial=0,
           edges=edges,boundaries=boundaries,
           conclusion=dict(widths='all positive',inputs='all fixed-sign mask cylinders and all signed bounds',
                           theorem='For every x in the cylinder with x <= bound, the source output y is in the cylinder, y <= bound, and x <= y.',
                           induction='Empty suffix, every nonsign column, then exactly one sign column'))
    replay(guard,c)
    return dict(status='certificate_produced',certificate=c)
