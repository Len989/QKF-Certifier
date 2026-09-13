"""Propose a finite prefix cover and a balanced observation-union certificate."""
from joint_kernel import SCHEMA,validate_spec,digest,cell,join,empty,answer


def cover(lo,hi,width):
    while lo<=hi:
        alignment=width if lo==0 else (lo&-lo).bit_length()-1
        free=min(alignment,(hi-lo+1).bit_length()-1)
        yield lo,free;lo+=1<<free


def produce(spec,query):
    w,s,_=validate_spec(spec)
    cells=[] if spec['lower']>spec['upper'] or spec['must']&~spec['may'] else [cell(spec,lo,n) for lo,n in cover(spec['lower']+s,spec['upper']+s,w)]
    values=[c['observation'] for c in cells];active=list(range(len(cells)));nodes=[]
    while len(active)>1:
        nxt=[]
        for i in range(0,len(active),2):
            if i+1==len(active):nxt.append(active[i]);continue
            a,b=active[i:i+2];value=join(values[a],values[b]);nodes.append(dict(left=a,right=b,observation=value))
            nxt.append(len(values));values.append(value)
        active=nxt
    root=active[0] if active else None;observed=values[root] if root is not None else empty()
    return dict(schema=SCHEMA,spec=dict(spec),query=dict(query),binding=digest([spec,query]),cells=cells,joins=nodes,root=root,
                answer=answer(spec,query,observed,cells))
