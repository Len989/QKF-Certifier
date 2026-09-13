"""Request only observations visible to the actual consumer; keep refusals."""
from qkf_certifier.kernel import children,at,replace,digest
from symbolic_bridge import path_guards
from regular_interfaces import order
from prefix_masks import lower,allowed_node
import context_producer as OLD
import result_kernel as K


def produce(initial,mode,authority=None):
    if mode not in {'baseline','sign','observed'}:raise ValueError('result mode')
    root,trace,stats=OLD.produce(initial,'context',authority)
    if mode=='baseline':return root,trace,stats
    requests=[];choices=[];cache={};hard={'sdiv','udiv','urem','srem'}
    def measure(e):return [sum(not allowed_node(n) for n in order(lower(e))),len(order(e))]
    def attempt(path):
        nonlocal root
        e=at(root,path)
        if not measure(e)[0]:return False
        kinds=[]
        if K.sign_consumer(e) is not None:kinds.append(('sign',None))
        if mode=='observed' and e[0] in {'urem','udiv'}:kinds.append(('division-action',None))
        if mode=='observed' and e[0] in hard:kinds.append(('word',None))
        action_view=K.native(e)
        if mode=='observed' and action_view[0] in K.ACTION.SHIFTS | K.ACTION.MASKS:
            kinds.extend(('action-on-word',dict(selector=t)) for t in order(action_view[2]) if t[0]=='select')
        if not kinds:return False
        guards=path_guards(root,path);options=[]
        for kind,parameter in kinds[:32]:
            key=(e,tuple(guards),kind,digest(parameter))
            if key not in cache:
                try:
                    after,p=K.derive(e,guards,kind,parameter,authority)
                    if measure(after)[0]>=measure(e)[0]:raise ValueError('request did not reduce unsupported operations')
                    cache[key]=(after,p)
                    requests.append(dict(kind=kind,source_hash=digest(e),guards_hash=digest(guards),status='covered'))
                except ValueError as ex:
                    cache[key]=None;requests.append(dict(kind=kind,source_hash=digest(e),guards_hash=digest(guards),status='unresolved',reason=str(ex)))
            if cache[key] is not None:
                after,p=cache[key];options.append(dict(kind=kind,parameter=parameter,after=after,proof=p,cost=measure(after)+[K.proof_steps(p)]))
        if not options:return False
        q=min(options,key=lambda x:x['cost']);nxt=replace(root,path,q['after'])
        trace.append(dict(schema=K.SCHEMA,minimum_width=2,path=path,kind=q['kind'],parameter=q['parameter'],guards=guards,
                          before_hash=digest(root),after_hash=digest(nxt),after=q['after'],proof=q['proof']))
        choices.append(dict(path=path,kind=q['kind'],cost=q['cost']));root=nxt
        if len(trace)>1000:raise ValueError('result rewrite budget')
        return True
    def visit(path):
        while attempt(path):pass
        for i in children(at(root,path)):visit(path+[i])
        if attempt(path):visit(path)
    visit([])
    return root,trace,dict(stats,result_requests=requests,result_choices=choices,
                          accepted=len(trace),selected_proof_steps=sum(K.proof_steps(t['proof']) for t in trace))
