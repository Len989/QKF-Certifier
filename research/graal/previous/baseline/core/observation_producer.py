"""Untrusted bounded choice among frozen sufficient observations."""
from qkf_certifier.kernel import at,replace,digest,children
from regular_interfaces import order
from prefix_masks import lower,allowed_node
import observation_kernel as K


def cost(after,proof):
    nodes=order(lower(after));unsupported=sum(not allowed_node(t) for t in nodes)
    # A proxy declared before evaluation, not a prediction of measured runtime.
    comparisons=sum(t[0].startswith('cmp') for t in nodes)
    state_bits=sum(t[0] in {'add','sub','shl','lshr','ashr'} or t[0].startswith('run_') for t in nodes)
    return [unsupported,comparisons,state_bits,len(nodes),K.proof_steps(proof)]


def choices(e,mode):
    yield 'supporting-bridge',{}
    if e[0]=='mul':
        if mode=='adaptive':yield 'joint-binary',{}
        for side in (1,2):
            for observation in (['exact'] if mode=='fixed' else ['zero','parity','exact']):
                yield 'finite-row',dict(side=side,observation=observation)
    if e[0]=='sdiv' and e[1]==K.ONE:
        for merge in ([False] if mode=='fixed' else [False,True]):yield 'unit-division',dict(merge=merge)
    if e[0]=='shl':
        for rep in (['mask'] if mode=='fixed' else ['mask','carry']):yield 'boundary',dict(representation=rep)


def produce(initial,mode):
    if mode not in {'baseline','fixed','adaptive'}:raise ValueError('selection mode')
    if mode=='baseline':return initial,[],dict(trials=[],attempts=0,accepted=0)
    root=initial;trace=[];trials=[];attempts=0
    def attempt(path):
        nonlocal root,attempts
        before=at(root,path);accepted=[];rejected=[]
        for kind,parameter in choices(before,mode):
            attempts+=1
            try:after,p,guards=K.derive(root,path,kind,parameter)
            except ValueError as e:
                if str(e).startswith('{'):rejected.append(dict(kind=kind,parameter=parameter,obstruction=__import__('json').loads(str(e))))
                continue
            if after==before:continue
            candidate=dict(kind=kind,parameter=parameter,after=after,proof=p,guards=guards,cost=cost(after,p))
            accepted.append(candidate)
            if mode=='fixed':break
        if not accepted:
            if rejected:trials.append(dict(path=path,before=digest(before),accepted=[],rejected=rejected))
            return False
        selected=min(accepted,key=lambda c:c['cost']) if mode=='adaptive' else accepted[0]
        trials.append(dict(path=path,before=digest(before),
           accepted=[{k:c[k] for k in ['kind','parameter','cost']} for c in accepted],rejected=rejected,
           selected=dict(kind=selected['kind'],parameter=selected['parameter'],cost=selected['cost'])))
        after=replace(root,path,selected['after'])
        trace.append(dict(schema=K.SCHEMA,minimum_width=2,path=path,kind=selected['kind'],parameter=selected['parameter'],
                          after=selected['after'],proof=selected['proof'],guards=selected['guards'],
                          before_hash=digest(root),after_hash=digest(after)))
        root=after
        if len(trace)>1000:raise RuntimeError('observation rewrite budget')
        return True
    def visit(path):
        while attempt(path):pass
        for i in children(at(root,path)):visit(path+[i])
        if attempt(path):visit(path)
    visit([])
    return root,trace,dict(trials=trials,attempts=attempts,accepted=len(trace),
                          selected_proof_steps=sum(K.proof_steps(t['proof']) for t in trace))
