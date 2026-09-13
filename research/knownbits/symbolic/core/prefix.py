"""Trusted nonzero observation bridge. No search or producer imports.

The proposed count is NOT an axiom. Four old word/integer proof obligations
establish a free-bit kernel cell, a named nonzero cell, membership in its
fiber, and bounds for the count decoder. A generic ground DAG then forces
the output observation. Only this checked observation permits substitution.
"""
import copy
import kernel
import bridge
import ground_checker
from transport import action, transported_kind

SCHEMA='qkf-nonzero-observation-certificate-v5'
MAX_CANDIDATES=4


def ground_source():
    row=lambda a:['row',a]
    meet=lambda a,b:['meet',a,b]
    join=lambda a,b:['join',a,b]
    return dict(schema='qkf-ground-obligation-v1',constants=['zero','L','r','B','a','C'],
                signature=dict(row=1,meet=2,join=2),equations=[
                    [row('L'),'zero'],[row('zero'),'zero'],
                    [meet('r','L'),'r'],[meet('r','zero'),'zero'],
                    [row(meet('r','L')),meet(row('r'),row('L'))],
                    [row(meet('r','zero')),meet(row('r'),row('zero'))],
                    [row('B'),'C'],[join('B','r'),'a'],
                    [row(join('B','r')),join(row('B'),row('r'))],
                    [join('C','zero'),'C']],query=[row('a'),'C'],
                interpretation='r is the free part of a; a=B OR r, r<=L; the captured row preserves meet/join/zero. Native identities are used only on named values.')


def describe(expr):
    if not isinstance(expr,list) or len(expr)!=2 or not isinstance(expr[0],str) or expr[0] not in {'clz','clo','ctz','cto'}:return None
    kind=expr[0];view=expr[1];reverse=flip=False;depth=0
    while isinstance(view,list) and len(view)==2 and view[0] in {'not','reverse'}:
        reverse^=view[0]=='reverse';flip^=view[0]=='not';view=view[1];depth+=1
        if depth>16:return None
    kind=transported_kind(kind,reverse,flip)
    if not isinstance(view,list) or len(view)!=3:return None
    if (kind,view[0]) not in {('clz','lshr'),('ctz','shl')}:return None
    base=action(kernel.tree(view[1]))
    if base is None:return None
    return dict(expression=copy.deepcopy(expr),kind=kind,shift=view[0],argument=copy.deepcopy(view[1]),
                amount=copy.deepcopy(view[2]),base_input=base[0],outer_reverse=reverse,outer_flip=flip)


def candidates(source):
    kernel.Compiler(source);found={};omitted=0
    def walk(value,path):
        nonlocal omitted
        d=describe(value)
        if d is not None:
            key=kernel.digest(d)
            if key not in found:
                if len(found)>=MAX_CANDIDATES:omitted+=1;return
                found[key]=dict(candidate_hash=key,descriptor=d,paths=[])
            found[key]['paths'].append(path);return
        if isinstance(value,list):
            for i,child in enumerate(value):walk(child,path+[i])
    walk(source['claims'],[])
    return list(found.values()),omitted


def validate_number(expr,source):
    """Bound syntax; proposed scalars may use only original base-word counts."""
    visited=0
    def scalar(e):
        nonlocal visited
        visited+=1
        if visited>256:raise ValueError('proposed number size')
        if type(e)is int:return
        if isinstance(e,str) and e in ['w']+source.get('parameters',[]):return
        if not isinstance(e,list) or not e:raise ValueError('proposed scalar')
        op=e[0]
        if op in {'clz','clo','ctz','cto'} and len(e)==2:
            view=['input',e[1]] if isinstance(e[1],str) else e[1]
            base=action(kernel.tree(view))
            if base is None or base[0] not in source['inputs']:raise ValueError('proposed count capture')
            return
        if op in {'add','sub','min','max'} and len(e)==3:scalar(e[1]);scalar(e[2]);return
        if op=='ite' and len(e)==4:boolean(e[1]);scalar(e[2]);scalar(e[3]);return
        raise ValueError('proposed scalar operation')
    def boolean(e):
        if type(e)is bool:return
        if not isinstance(e,list) or not e:raise ValueError('proposed Boolean')
        if e[0] in {'and','or'}:
            for c in e[1:]:boolean(c)
        elif e[0]=='not' and len(e)==2:boolean(e[1])
        elif e[0] in {'eq','le','lt'} and len(e)==3:scalar(e[1]);scalar(e[2])
        else:raise ValueError('proposed Boolean operation')
    scalar(expr)


def specification(source,candidate,number):
    validate_number(number,source)
    d=candidate['descriptor'];a=d['argument'];n=[d['kind'],a]
    leading=d['kind']=='clz'
    minus=lambda a,b:['sub',a,b]
    plus=lambda a,b:['add',a,b]
    point=lambda p:['and',['lowmask',plus(p,1)],['not',['lowmask',p]]]
    free_size=minus(minus('w',n),1)
    L=['lowmask' if leading else 'highmask',free_size]
    B=point(free_size if leading else n)
    C=point(minus(minus('w',number),1) if leading else number)
    observation=['highmask' if leading else 'lowmask',plus(number,1)]
    frames=[dict(operation='and',capture=observation,capture_sort='word',capture_environment='original_source'),
            dict(operation=d['shift'],capture=d['amount'],capture_sort='scalar',capture_environment='original_source')]
    r=['and',a,L]
    return dict(constants=dict(zero=['zero'],L=L,r=r,B=B,a=a,C=C),frames=frames,
                observation=observation,number=number,count_kind=d['kind'],
                native_rules=['captured_mask_preserves_meet_join_zero','captured_shift_preserves_meet_join_zero',
                              'named_free_part_meet_idempotence','named_meet_zero','named_join_zero',
                              'bounded_prefix_observation_decodes_count'])


def bridge_source(source,candidate,number):
    spec=specification(source,candidate,number);c=spec['constants']
    row=lambda value:bridge.row_apply(spec['frames'],value)
    return dict(schema=kernel.DSL,name='nonzero_prefix_native_bridge',inputs=copy.deepcopy(source['inputs']),
                parameters=copy.deepcopy(source.get('parameters',[])),assume=copy.deepcopy(source.get('assume',True)),
                claims=[['word_eq',row(c['L']),['zero']],['word_eq',row(c['B']),c['C']],
                        ['word_eq',['or',c['B'],c['r']],c['a']],
                        ['scalar',['and',['le',0,number],['le',number,'w']]]],
                origin=dict(source_hash=kernel.digest(source),candidate_hash=candidate['candidate_hash'],
                            native_map_hash=kernel.digest(spec)))


def residual(source,lemmas):
    replacements={tuple(path):entry['number'] for entry in lemmas for path in entry['candidate']['paths']}
    trace=[]
    def walk(value,path):
        if tuple(path) in replacements:
            result=copy.deepcopy(replacements[tuple(path)])
            trace.append(dict(path=path,rule='checked_nonzero_observation_count',before=value,after=result))
            return result
        return [walk(v,path+[i]) for i,v in enumerate(value)] if isinstance(value,list) else copy.deepcopy(value)
    result=copy.deepcopy(source);result['claims']=walk(source['claims'],[])
    return result,trace


def verify(source,cert):
    if cert.get('schema')!=SCHEMA or cert.get('source_hash')!=kernel.digest(source):raise ValueError('v5 source binding')
    available={c['candidate_hash']:c for c in candidates(source)[0]}
    lemmas=cert.get('lemmas')
    if not isinstance(lemmas,list) or len(lemmas)>MAX_CANDIDATES:raise ValueError('prefix lemma list')
    ground=cert.get('ground_certificate');ground_nodes=0
    if lemmas:ground_nodes=ground_checker.verify(ground_source(),ground)['proof_nodes']
    elif ground is not None:raise ValueError('unused nonzero ground proof')
    seen=set();native=bridge_nodes=0;details=[]
    for entry in lemmas:
        key=entry.get('candidate_hash')
        if key not in available or key in seen:raise ValueError('prefix candidate binding')
        seen.add(key);candidate=available[key]
        if entry.get('candidate')!=candidate:raise ValueError('prefix candidate or path changed')
        spec=specification(source,candidate,entry['number'])
        if entry.get('native_map_hash')!=kernel.digest(spec) or entry.get('native_rules')!=spec['native_rules']:
            raise ValueError('native observation bridge')
        result=kernel.verify(bridge_source(source,candidate,entry['number']),entry['bridge_certificate'])
        bridge_nodes+=result['proof_nodes'];native+=len(spec['native_rules']);details.append(result)
    transformed,trace=residual(source,lemmas)
    if cert.get('residual_hash')!=kernel.digest(transformed) or cert.get('rewrite_trace')!=trace:
        raise ValueError('prefix residual binding')
    tail=cert['tail'];backend=cert['tail_backend']
    if backend=='v3':
        final=kernel.verify(transformed,tail);tail_steps=final['proof_nodes']
    elif backend=='v4':
        final=bridge.verify(transformed,tail);tail_steps=final['total_recorded_steps']
    else:raise ValueError('tail backend')
    return dict(status='proved_under_original_source_assumptions',claims=len(source['claims']),lemmas=len(lemmas),
                bridge_proof_nodes=bridge_nodes,ground_dag_nodes=ground_nodes,ground_instantiations=len(lemmas),
                native_bridge_rules=native,rewrite_steps=len(trace),tail_backend=backend,tail_steps=tail_steps,
                total_recorded_steps=bridge_nodes+ground_nodes+len(lemmas)+native+len(trace)+tail_steps,
                bridge_results=details,tail_result=final)
