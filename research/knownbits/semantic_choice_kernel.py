"""Existing consumers accept checked, source-bound observation interfaces."""
from qkf_certifier.kernel import at,replace,digest
from regular_interfaces import tree
from symbolic_bridge import path_guards
import observation_kernel as OLD
import row_observation_kernel as ROW
from semantic_view import source_view,view

SCHEMA='qkf-observation-choice-v2-semantic'
ONE=OLD.ONE


def verify_cover(e,guards,c):
    if c['engine']=='rows':return ROW.verify(e,guards,c['certificate'])[0]
    if c['engine']!='views':raise ValueError('cover engine')
    v,g=source_view(e,guards);values,proof=OLD.support(v,g)
    if c['source_hash']!=digest(e) or c['guards_hash']!=digest(guards) or c['view_hash']!=digest(v):raise ValueError('view-only cover binding')
    if c['values']!=values or digest(c['proof'])!=digest(proof):raise ValueError('view-only cover premise')
    return values


def derive(initial,path,kind,parameter):
    if kind not in {'semantic-finite-row','semantic-joint-binary'}:return OLD.derive(initial,path,kind,parameter)
    e=at(initial,path);guards=path_guards(initial,path)
    if e[0]!='mul':raise ValueError('multiplier consumer')
    if kind=='semantic-finite-row':
        side=parameter['side'];obs=parameter['observation']
        if side not in (1,2) or obs not in {'zero','parity','exact'}:raise ValueError('row parameters')
        values=verify_cover(e[side],guards,parameter['cover'])
        if not values:
            return OLD.Z,dict(kind='semantic-empty-path',side=side,cover_certificate=parameter['cover'],minimum_width=2,
              justification='source-bound cover is empty under the actual branch guards; arbitrary word replacement is vacuous'),guards
        cells=[(k,OLD.multiply_cell(view(e[3-side]),k)) for k in values]
        groups,bad=OLD.partition_cells(cells,obs)
        if bad:raise ValueError(__import__('json').dumps(bad))
        after=OLD.emit_row(view(e[side]),groups)
        proof=dict(kind='semantic-finite-multiplier-row',side=side,cover=values,cover_certificate=parameter['cover'],
           supplied_cells=[dict(label=k,value=v) for k,v in cells],factor=groups,observation=obs,canonical_consumer=view(e),minimum_width=2)
    else:
        a=verify_cover(e[1],guards,parameter['left']);b=verify_cover(e[2],guards,parameter['right'])
        if not a or not b:
            return OLD.Z,dict(kind='semantic-empty-path',left=parameter['left'],right=parameter['right'],minimum_width=2,
              justification='one source-bound operand cover is empty under the actual branch guards'),guards
        if not set(a)<=set([0,1]) or not set(b)<=set([0,1]):raise ValueError('not a binary product carrier')
        cells=[dict(a=x,b=y,product=x*y,meet=x&y) for x in a for y in b]
        after=('and',view(e[1]),view(e[2]));proof=dict(kind='semantic-joint-binary',left=parameter['left'],right=parameter['right'],cells=cells,minimum_width=2)
    return after,proof,guards


def proof_steps(proof):
    if not proof['kind'].startswith('semantic-'):return OLD.proof_steps(proof)
    def count(v):
        if isinstance(v,dict):return 1+sum(count(x) for x in v.values())
        if isinstance(v,list):return sum(count(x) for x in v)
        return 0
    return count(proof)


def replay(initial,trace,expected):
    if not isinstance(trace,list) or len(trace)>1000:raise ValueError('observation trace limit')
    root=initial;steps=0
    for t in trace:
        if t['schema']==OLD.SCHEMA:
            nxt=replace(root,t['path'],tree(t['after']));root,n=OLD.replay(root,[t],nxt);steps+=n;continue
        if t['schema']!=SCHEMA or t['minimum_width']!=2 or t['before_hash']!=digest(root):raise ValueError('semantic observation binding')
        after,p,guards=derive(root,t['path'],t['kind'],t['parameter'])
        if digest(p)!=digest(t['proof']) or digest(guards)!=digest(t['guards']) or after!=tree(t['after']):raise ValueError('semantic observation derivation')
        root=replace(root,t['path'],after);steps+=proof_steps(p)
        if t['after_hash']!=digest(root):raise ValueError('semantic observation result binding')
    if root!=tree(expected):raise ValueError('semantic observation final expression')
    return root,steps
