"""Search-free, source-bound instantiation of a proved quotient representative.

No shift cancellation is trusted as an axiom: the universal word theorem
and both instance conditions are replayed by the unchanged v3 checker.
"""
import copy
import kernel
import prefix
import ground_checker

SCHEMA='qkf-word-reconstruction-certificate-v6'
MAX_CANDIDATES=4


def factor_source(direction):
    if direction not in {'left','right'}:raise ValueError('factor direction')
    first,second,mask=('shl','lshr','lowmask') if direction=='left' else ('lshr','shl','highmask')
    z=['input','z']
    return dict(schema=kernel.DSL,name='universal_retained_representative_'+direction,
                inputs=['z'],parameters=['s'],assume=['and',['le',0,'s'],['le','s','w']],
                claims=[['word_eq',[second,[first,z,'s'],'s'],['and',z,[mask,['sub','w','s']]]]])


def ground_source():
    return dict(schema='qkf-ground-obligation-v1',constants=['a'],signature=dict(forward=1,back=1,projection=1),
                equations=[[['back',['forward','a']],['projection','a']],[['projection','a'],'a']],
                query=[['back',['forward','a']],'a'])


def describe(expr):
    if not isinstance(expr,list) or len(expr)!=3 or not isinstance(expr[0],str):return None
    outer=expr[0];inner=expr[1]
    if outer not in {'lshr','shl'} or not isinstance(inner,list) or len(inner)!=3:return None
    if inner[0]!=('shl' if outer=='lshr' else 'lshr') or inner[2]!=expr[2]:return None
    return dict(expression=copy.deepcopy(expr),argument=copy.deepcopy(inner[1]),amount=copy.deepcopy(expr[2]),
                direction='left' if outer=='lshr' else 'right')


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


def substitution(candidate):
    d=candidate['descriptor']
    return dict(factor_key=d['direction'],word_substitution={'z':copy.deepcopy(d['argument'])},
                scalar_substitution={'s':copy.deepcopy(d['amount'])},width='w',capture_environment='original_source')


def instance_source(source,candidate):
    d=candidate['descriptor'];s=d['amount'];a=d['argument']
    prefix.validate_number(s,source)
    mask='lowmask' if d['direction']=='left' else 'highmask'
    return dict(schema=kernel.DSL,name='retained_representative_membership',inputs=copy.deepcopy(source['inputs']),
                parameters=copy.deepcopy(source.get('parameters',[])),assume=copy.deepcopy(source.get('assume',True)),
                claims=[['scalar',['and',['le',0,s],['le',s,'w']]],
                        ['word_eq',['and',a,[mask,['sub','w',s]]],a]],
                origin=dict(source_hash=kernel.digest(source),candidate_hash=candidate['candidate_hash'],
                            substitution_hash=kernel.digest(substitution(candidate))))


def residual(source,lemmas):
    replacements={tuple(path):entry['candidate']['descriptor']['argument'] for entry in lemmas for path in entry['candidate']['paths']}
    trace=[]
    def walk(value,path):
        if tuple(path) in replacements:
            result=copy.deepcopy(replacements[tuple(path)])
            trace.append(dict(path=path,rule='checked_retained_representative',before=value,after=result));return result
        return [walk(child,path+[i]) for i,child in enumerate(value)] if isinstance(value,list) else copy.deepcopy(value)
    result=copy.deepcopy(source);result['claims']=walk(source['claims'],[])
    return result,trace


def verify(source,cert):
    if cert.get('schema')!=SCHEMA or cert.get('source_hash')!=kernel.digest(source):raise ValueError('v6 source binding')
    available={c['candidate_hash']:c for c in candidates(source)[0]};lemmas=cert.get('lemmas')
    if not isinstance(lemmas,list) or not 0<len(lemmas)<=MAX_CANDIDATES:raise ValueError('reconstruction lemma list')
    factors=cert.get('factor_certificates');required={entry['candidate']['descriptor']['direction'] for entry in lemmas}
    if not isinstance(factors,dict) or set(factors)!=required:raise ValueError('factor coverage')
    factor_nodes=sum(kernel.verify(factor_source(direction),proof)['proof_nodes'] for direction,proof in factors.items())
    ground_nodes=ground_checker.verify(ground_source(),cert['ground_certificate'])['proof_nodes']
    seen=set();instance_nodes=0
    for entry in lemmas:
        key=entry.get('candidate_hash')
        if key not in available or key in seen:raise ValueError('reconstruction candidate binding')
        seen.add(key);candidate=available[key]
        if entry.get('candidate')!=candidate or entry.get('substitution')!=substitution(candidate):raise ValueError('captured substitution binding')
        instance_nodes+=kernel.verify(instance_source(source,candidate),entry['instance_certificate'])['proof_nodes']
    transformed,trace=residual(source,lemmas)
    if cert.get('residual_hash')!=kernel.digest(transformed) or cert.get('rewrite_trace')!=trace:raise ValueError('reconstruction residual binding')
    final=prefix.verify(transformed,cert['tail'])
    # One universal instantiation and one ground instantiation per candidate;
    # every rewritten consumer is counted separately. No new native axiom.
    return dict(status='proved_under_original_source_assumptions',claims=len(source['claims']),lemmas=len(lemmas),
                factor_proof_nodes=factor_nodes,instance_proof_nodes=instance_nodes,ground_dag_nodes=ground_nodes,
                universal_instantiations=len(lemmas),ground_instantiations=len(lemmas),rewrite_steps=len(trace),
                tail_steps=final['total_recorded_steps'],tail_result=final,
                total_recorded_steps=factor_nodes+instance_nodes+ground_nodes+2*len(lemmas)+len(trace)+final['total_recorded_steps'])
