"""Candidate selection for the checked consumer-requested boundary interface."""
import collections
from qkf_certifier.kernel import children,at,replace,digest
from symbolic_bridge import path_guards
from regular_interfaces import order
from prefix_masks import lower,allowed_node
import semantic_choice_producer as PREVIOUS
import boundary_v2_kernel as K


def cost(e,proof):
    ns=order(lower(e))
    return [sum(not allowed_node(t) for t in ns),sum(t[0].startswith('cmp') for t in ns),
        sum(t[0] in {'add','sub','shl','lshr','ashr'} or t[0].startswith('run_') for t in ns),len(ns),K.proof_steps(proof)]


def produce(initial,mode):
    root,trace,old_stats=PREVIOUS.produce(initial,'rows')
    if mode=='previous':return root,trace,old_stats
    if mode not in {'endpoints','boundary'}:raise ValueError('boundary mode')
    queries=[];cache={};selected=[];failures=collections.Counter()
    def attempt(path):
        nonlocal root
        e=at(root,path)
        if e[0] not in K.ACTIONS:return False
        try:ns=K.counts(K.native(e[2]))
        except ValueError as ex:
            failures[str(ex)]+=1
            queries.append(dict(action=e[0],source_hash=digest(e),amount_hash=digest(e[2]),
                engine='request',status='unresolved',reason=str(ex)))
            return False
        if not ns:return False
        guards=path_guards(root,path);options=[]
        for engine in (['endpoints'] if mode=='endpoints' else ['endpoints','position']):
            key=(e,tuple(guards),engine)
            if key not in cache:
                request=dict(action=e[0],source_hash=digest(e),amount_hash=digest(e[2]),guards_hash=digest(guards),engine=engine)
                try:
                    after,proof=K.derive(e,guards,engine);cache[key]=(after,proof)
                    queries.append(dict(request,status='covered',after_hash=digest(after),proof_kind=proof['kind']))
                except ValueError as ex:
                    cache[key]=None;failures[str(ex)]+=1;queries.append(dict(request,status='unresolved',reason=str(ex)))
            if cache[key] is None:continue
            after,proof=cache[key]
            if after==e:continue
            options.append(dict(engine=engine,after=after,proof=proof,cost=cost(after,proof)))
        if not options:return False
        choice=min(options,key=lambda r:r['cost']);nxt=replace(root,path,choice['after'])
        trace.append(dict(schema=K.SCHEMA,minimum_width=2,path=path,engine=choice['engine'],guards=guards,
            before_hash=digest(root),after_hash=digest(nxt),after=choice['after'],proof=choice['proof']))
        selected.append(dict(path=path,source_hash=digest(e),choices=[dict(engine=o['engine'],cost=o['cost']) for o in options],
            engine=choice['engine'],cost=choice['cost']))
        root=nxt
        if len(trace)>1000:raise ValueError('boundary rewrite budget')
        return True
    def visit(path):
        while attempt(path):pass
        for i in children(at(root,path)):visit(path+[i])
        if attempt(path):visit(path)
    visit([])
    return root,trace,dict(old_stats,boundary_queries=queries,boundary_choices=selected,boundary_failures=dict(failures),
        accepted=len(trace),selected_proof_steps=sum(K.proof_steps(t['proof']) for t in trace))
