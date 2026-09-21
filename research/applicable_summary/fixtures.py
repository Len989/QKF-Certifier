"""PR45 fixed functional population, registered before implementation runs."""
from pathlib import Path
from research.source_lemmas.fixtures import MASK, PARITY, goals, batch
from research.source_query.fixtures import target
from research.source_query.context import make_request

BASE = 'd53500cac8788a221eb657e239c105834439087c'
SIGNED = 'modular-lsb-signed-word-predicates-v1'
PHASE = 'graal-ascending-physical-phases-v1'

def request(query, profile=SIGNED):
    return dict(schema='qkf-summary-request-v1', profile=profile, query=query)

def cases():
    def signed(name, source, selected, status='certified', *, width=None, guards=None,
               route=None, limits=None, mode='build', applications=None):
        q = batch(source, selected, width=width, guards=guards)
        return dict(name=name, source=source, request=request(q), expected=status,
                    route=route, limits=limits, mode=mode, applications=applications or [])
    yield signed('mask_all', MASK, goals()[:1], applications=[dict(input=0,width=8,output=False),dict(input=128,width=8,output=True),dict(input=1,width=1,output=True)])
    yield signed('parity_fixed8_reuse', PARITY, goals()[:4], width=8, route='reuse', applications=[dict(input=128,width=8,output=True)])
    yield signed('mask_direct', MASK, goals()[:4], route='direct_cache', applications=[dict(input=0,width=3,output=False)])
    yield signed('mask_refuted', MASK.replace('(x&7)==0','(x&7)==1'), goals()[:1], 'refuted', width=8)
    yield signed('empty', MASK, goals()[:1], 'verified_empty_domain', guards=[['negative'],['nonnegative']])
    yield signed('unsupported', 'class Demo { static boolean f(long x) { long unused=x>>1; return x<0; } }', goals()[:1], 'unsupported')
    yield signed('budget', MASK, goals()[:1], 'unresolved', limits=dict(max_work=0))
    power='class Demo { static boolean f(long x) { return (x&(x-1))==0; } }'
    yield signed('representation_gap', power, [['popcount_le',1]], 'unresolved', guards=[])
    yield signed('horizon', MASK, goals()[:1], 'unresolved', limits=dict(max_horizon=0))
    yield signed('import_pr41', MASK, goals()[:1], mode='import41', applications=[dict(input=128,width=8,output=True)])
    yield signed('import_pr43', PARITY, goals()[:1], mode='import43', applications=[dict(input=128,width=8,output=True)])
    yield signed('import_pr44', MASK, goals()[:4], route='reuse', mode='import44', applications=[dict(input=128,width=8,output=True)])
    yield signed('import_coverage', power, [['popcount_le',1]], guards=[], mode='import_coverage', applications=[dict(input=0,width=8,output=True),dict(input=3,width=8,output=False)])
    source=Path('research/graal/previous/baseline/source/IntegerStamp.java').read_text()
    for name, route, goal, status, limits in [
        ('phase_direct',None,[3,0],'certified',None),
        ('phase_forcing','forcing',[3,0],'certified',None),
        ('phase_unresolved','no_saturation',[3,0],'unresolved',None),
        ('phase_refuted',None,[3,1],'refuted',None),
        ('phase_budget','forcing',[3,0],'unresolved',dict(max_work=0))]:
        query=dict(schema='qkf-local-forcing-request-v1',profile=PHASE,label=[0,1,1,0],goals=[goal])
        yield dict(name=name,source=source,request=request(query,PHASE),expected=status,route=route,limits=limits,mode='build',applications=[dict(input=3,output=0)] if status=='certified' else [])
