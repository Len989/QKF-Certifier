"""Bounded requests for scoped carriers; no program names or targets are used."""
import collections
from functools import lru_cache
from qkf_certifier.kernel import children,at,replace,digest
from symbolic_bridge import path_guards
from regular_interfaces import order
import boundary_v2_producer as PREVIOUS
import context_kernel as K


@lru_cache(maxsize=10000)
def intrinsic_candidates(y):
    out=[]
    if y[0]=='shl' and y[1]==K.ONE:out.append(dict(unit_shift=y))
    if y[0]=='and':
        for x in order(y)[:64]:
            for op in ('countr_zero','countr_one'):
                n=K.native((op,x))
                if n[0] not in {'countr_zero','countr_one'}:continue
                arithmetic,_=K.NATIVE_ROWS.boundary(('shl',K.ONE,n),'carry')
                if K.native(arithmetic)==y:out.append(dict(boundary_count=n))
    return out


def candidates(y, guards):
    yield from intrinsic_candidates(y)
    yield dict(predecessor=K.native(('sub',y,K.ONE)),route='definition')
    edges = K.equality_edges(K.facts(guards)); adjacency = collections.defaultdict(list)
    for e in edges:
        adjacency[e['left']].append((e['right'],e['difference'],e['guard']))
        adjacency[e['right']].append((e['left'],-e['difference'],e['guard']))
    queue = collections.deque([(y,0,[])]); visited={(y,0)}
    while queue and len(visited) <= 128:
        x,offset,route=queue.popleft()
        if route and offset==1:
            yield dict(predecessor=x,route=route)
        if len(route)>=K.MAX_ROUTE: continue
        for other,delta,g in adjacency[x]:
            key=(other,offset+delta)
            if key in visited: continue
            visited.add(key)
            queue.append((other,offset+delta,route+[dict(guard=g,**{'from':x,'to':other})]))


def produce(initial,mode,authority=None):
    if mode not in {'baseline','guards','context'}: raise ValueError('context mode')
    root,trace,old_stats=PREVIOUS.produce(initial,'boundary')
    if mode=='baseline': return root,trace,old_stats
    scope=None if mode=='guards' else authority
    if mode=='context' and scope is None: raise ValueError('missing source authority')
    requests=[];choices=[];failures=collections.Counter();cache={}
    def attempt(path):
        nonlocal root
        e=at(root,path)
        if e[0] not in K.CONSUMERS: return False
        v=K.native(e);guards=path_guards(root,path)
        counts=[t for t in order(v) if t[0] in K.COUNTS]
        options=[]
        # A source selector supplies a finite row of named words. Only keep
        # a proposal when cell identities actually eliminate a costly consumer.
        hard={'mul','udiv','sdiv','urem','srem'}
        before_hard=sum(t[0] in hard for t in order(v))
        difficult=lambda t:t[0] in hard or t[0].startswith('count')
        before_difficult=sum(difficult(t) for t in order(v))
        extras=[]
        if v[0]=='lshr' and v[2][0]=='countr_one':
            extras.append(dict(observed_action='lowest-set-bit-erasure'))
        if before_hard:
            extras += [dict(selector=t) for t in order(v) if t[0]=='select'][:32]
        if v[0]=='urem':
            extras += [dict(sparse_divisor=p) for p in candidates(v[2],guards)]
        for parameter in extras:
            key=(e,'extra',digest(parameter),tuple(guards))
            if key not in cache:
                try:
                    after,proof=K.derive(e,guards,scope,parameter)
                    if sum(difficult(t) for t in order(after))>=before_difficult:
                        raise ValueError('no consumer eliminated by this source row')
                    cache[key]=(after,proof,parameter)
                    requests.append(dict(source_hash=digest(e),parameter=parameter,status='covered'))
                except ValueError as ex:
                    cache[key]=None;failures[str(ex)]+=1
                    requests.append(dict(source_hash=digest(e),parameter=parameter,status='unresolved',reason=str(ex)))
            if cache[key] is not None:
                after,proof,param=cache[key]
                options.append(dict(after=after,proof=proof,parameter=param,
                    cost=[sum(difficult(t) for t in order(after)),len(order(after)),K.proof_steps(proof)]))
        for n in counts:
            key=(e,n,tuple(guards))
            if key not in cache:
                candidates_tried=[];found=None
                for premises in candidates(n[1],guards):
                    parameter=dict(count=n,premises=premises)
                    try:
                        after,proof=K.derive(e,guards,scope,parameter)
                        candidates_tried.append(dict(parameter=parameter,status='covered'))
                        found=(after,proof,parameter);break
                    except ValueError as ex:
                        failures[str(ex)]+=1
                        candidates_tried.append(dict(parameter=parameter,status='unresolved',reason=str(ex)))
                requests.append(dict(source_hash=digest(e),count=n,guards_hash=digest(guards),
                                     candidates=candidates_tried,status='covered' if found else 'unresolved'))
                cache[key]=found
            if cache[key] is None: continue
            after,proof,parameter=cache[key]
            if after==e: continue
            cost=[
                sum(difficult(t) for t in order(after)),len(order(after)),K.proof_steps(proof)]
            options.append(dict(after=after,proof=proof,parameter=parameter,cost=cost))
        if not options:return False
        chosen=min(options,key=lambda r:r['cost']);nxt=replace(root,path,chosen['after'])
        trace.append(dict(schema=K.SCHEMA,minimum_width=2,policy=mode,path=path,guards=guards,
            parameter=chosen['parameter'],before_hash=digest(root),after_hash=digest(nxt),
            after=chosen['after'],proof=chosen['proof']))
        choices.append(dict(path=path,source_hash=digest(e),parameter=chosen['parameter'],cost=chosen['cost']))
        root=nxt
        if len(trace)>1000:raise ValueError('context rewrite budget')
        return True
    def visit(path):
        while attempt(path):pass
        for i in children(at(root,path)):visit(path+[i])
        if attempt(path):visit(path)
    visit([])
    return root,trace,dict(old_stats,context_requests=requests,context_choices=choices,
                          context_failures=dict(failures),accepted=len(trace),
                          selected_proof_steps=sum(K.proof_steps(t['proof']) for t in trace))
