"""Untrusted template builder and finite congruence/model experiments."""
import json
from collections import deque
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'core'))
import prefix
import ground_checker
from kernel_saturation import produce as zero_produce,lower_model


def generated_relations(width,relations):
    size=1<<width;parent=list(range(size));pending=deque()
    def find(a):
        while parent[a]!=a:parent[a]=parent[parent[a]];a=parent[a]
        return a
    def merge(a,b):
        x,y=find(a),find(b)
        if x!=y:parent[y]=x;pending.append((a,b))
    for a,b in relations:merge(a,b)
    while pending:
        a,b=pending.popleft()
        for c in range(size):merge(a&c,b&c);merge(a|c,b|c)
    return [find(a) for a in range(size)]


def produce(source):
    # Same 19-node zero-fiber proof, instantiated on r and L, then lifted
    # through the join with a named representative B of the nonzero fiber.
    renamed=dict(source,equations=source['equations'][:6],query=[['row','r'],'zero'])
    old=zero_produce(renamed)
    # The v3 builder has one explicit refl term row(a); adapt this term.
    for node in old['nodes']:
        if node['kind']=='refl':node['term']=['row','r']
    nodes=old['nodes'];zero_root=old['root']
    def emit(kind,**fields):nodes.append(dict(kind=kind,**fields));return len(nodes)-1
    supplied=emit('input',equation=6);decomp=emit('input',equation=7)
    compatibility=emit('input',equation=8);native_zero=emit('input',equation=9)
    lifted=emit('congr',operation='row',premises=[decomp])
    reflected=emit('sym',premise=lifted)
    start=emit('trans',left=reflected,right=compatibility)
    cells=emit('congr',operation='join',premises=[supplied,zero_root])
    step=emit('trans',left=start,right=cells)
    root=emit('trans',left=step,right=native_zero)
    return dict(schema='qkf-ground-dag-v1',source_hash=ground_checker.digest(source),nodes=nodes,root=root)


def main():
    source=prefix.ground_source();cert=produce(source)
    proof=ground_checker.verify(source,cert)
    model=lower_model(source,1);lower=ground_checker.verify_model(source,model,1)
    assert model['constants']['C']!=model['constants']['zero']
    masks=pairs=forced_points=growing_nonzero_rows=0;rejected=0
    for w in range(1,6):
        size=1<<w
        for L in range(size):
            for B in range(size):
                if L&B:continue
                for C in [0,1]:
                    if B==0 and C!=0:rejected+=1;continue
                    S={0,L,B,L|B};killer=(L|B) if C==0 else L
                    value=lambda a:0 if a in {0,L} else C
                    relations=[(a,b) for a in S for b in S if value(a)==value(b)]
                    classes=generated_relations(w,relations)
                    for a in range(size):
                        for b in range(size):
                            assert (classes[a]==classes[b])==((a&~killer)==(b&~killer));pairs+=1
                    actual={a for a in range(size) if any(classes[a]==classes[b] for b in S)}
                    expected={a for a in range(size) if ((a&~killer)==0 if C==0 else (a&~L) in {0,B})}
                    assert actual==expected
                    forced_points+=len(actual);masks+=1
                    if C and len(actual)>len(S):growing_nonzero_rows+=1
    # A zero-prefix-only interface omits the stop cell and cannot distinguish
    # these words. n=1 is the supplied zero-run length, not the true count
    # of the second completion once the missing stop cell is restored.
    weak=dict(width=4,shift=1,supplied_zero_prefix_length=1,inputs=[4,0],outputs=[2,0],actual_output_clz=[2,4])
    report=dict(status='passed',ground=proof,lower_horizon=lower,lower_has_nonzero_C=True,
                finite_rows=masks,kernel_pairs=pairs,forced_points=forced_points,
                growing_nonzero_rows=growing_nonzero_rows,rejected_inconsistent_B_zero_C_nonzero=rejected,
                weak_prefix_interface=weak,
                scope='Exact finite ground horizon 2 for this ten-equation presentation; finite checks of the explicit kernel formulas at w=1..5.')
    out=ROOT/'results/nonzero_ground';out.mkdir(parents=True,exist_ok=True)
    for name,obj in [('obligation',source),('certificate',cert),('lower_model',model),('validation',report)]:
        (out/(name+'.json')).write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
