"""Bounded query-local inference of source-forced value observations."""
import collections
from qkf_certifier.kernel import digest
from regular_interfaces import order
from semantic_view import source_view,branch,literal,TRUE,FALSE
import row_observation_kernel as K


def reachability(es):
    nodes={e[k] for e in es for k in ['a','b']};result={}
    for kind in ['eq','u','s']:
        for start in sorted(nodes,key=repr):
            seen={(start,False):[]};queue=collections.deque([(start,False)])
            while queue:
                node,strict=queue.popleft();path=seen[node,strict]
                for i,e in enumerate(es):
                    if e['kind']!=kind or e['a']!=node:continue
                    nxt=(e['b'],strict or bool(e['strict']))
                    if nxt not in seen:seen[nxt]=path+[i];queue.append(nxt)
            for (end,strict),path in seen.items():result[kind,start,end,strict]=path
    return result


def impossible(ctx,es,paths):
    for i,(p,t) in enumerate(ctx):
        if (p==TRUE and not t) or (p==FALSE and t):return dict(rule='false-guard',guard=i)
    for (kind,a,b,strict),path in paths.items():
        if kind=='eq':continue
        delta=sum(es[i]['strict'] for i in path)
        if a==b and delta:return dict(rule='strict-cycle',kind=kind,a=a,b=b,path=path)
        x,y=K.cut_value(a,kind),K.cut_value(b,kind)
        if x is not None and y is not None and x+delta>y:return dict(rule='constant-order-conflict',kind=kind,a=a,b=b,path=path)
        if kind=='u' and y is not None and y-delta<0:return dict(rule='unsigned-below-zero',kind=kind,a=a,b=b,path=path)
    return None


def carrier(e,ctx,es,paths):
    proposals=[]
    for (kind,a,b,strict),path in paths.items():
        if kind=='eq' and a==e and literal(b) is not None and abs(literal(b))<=K.MAX_LABEL:
            proposals.append(dict(rule='equal-literal',literal=b,path=path))
    for kind in ['u','s']:
        lowers=[(0,None)] if kind=='u' else [];uppers=[]
        for (domain,a,b,strict),path in paths.items():
            if domain!=kind:continue
            delta=sum(es[i]['strict'] for i in path)
            if a==e and K.cut_value(b,kind) is not None:uppers.append((K.cut_value(b,kind)-delta,dict(constant=b,path=path)))
            if b==e and K.cut_value(a,kind) is not None:lowers.append((K.cut_value(a,kind)+delta,dict(constant=a,path=path)))
        if lowers and uppers:
            lo,lp=max(lowers,key=lambda p:p[0]);hi,hp=min(uppers,key=lambda p:p[0])
            if lo<=hi:proposals.append(dict(rule='order-interval',kind=kind,lower=lp,upper=hp))
    if e[0]=='and':
        for side in (1,2):
            k=literal(e[side])
            if k is not None and 0<=k<=3:proposals.append(dict(rule='constant-bit-mask',side=side))
    accepted=[]
    for p in proposals:
        try:values=K.carrier_values(e,ctx,p);accepted.append(dict(term=e,values=values,proof=p))
        except ValueError:pass
    if not accepted:raise ValueError('no finite carrier for '+e[0])
    return min(accepted,key=lambda r:(len(r['values']),repr(r['values']),repr(r['proof'])))


def leaf(e,ctx,es,paths):
    carriers={}
    def visit(t):
        if literal(t) is not None:return
        if t in carriers:return
        try:carriers[t]=carrier(t,ctx,es,paths);return
        except ValueError:pass
        if t[0] not in K.OPS:raise ValueError('no finite carrier for '+t[0])
        for x in t[1:]:visit(x)
    visit(e);cs=sorted(carriers.values(),key=lambda c:repr(c['term']));rows,joins=K.glue_rows(e,cs);values=K.cover(rows)
    return dict(kind='finite-row',carriers=cs,rows=rows,values=values)


def produce(expr,guards):
    root,ctx=source_view(expr,guards);nodes=0
    def walk(e,g):
        nonlocal nodes
        nodes+=1
        if nodes>K.MAX_NODES:raise ValueError('observation proof tree budget')
        if len(order(e))>256 or len(g)>64:raise ValueError('query/context budget')
        es=K.edges(g);paths=reachability(es);bad=impossible(g,es,paths)
        if bad:return dict(kind='impossible',proof=bad,values=[])
        selectors=[t for t in order(e) if t[0]=='select']
        if not selectors:return leaf(e,g,es,paths)
        # Innermost choices first: their equations replace every shared use,
        # including occurrences in surrounding branch conditions.
        selector=min(selectors,key=lambda t:(len(order(t)),repr(t)));children={}
        for truth,key in [(True,'true'),(False,'false')]:
            nxt,ng=branch(e,g,selector,truth);children[key]=walk(nxt,ng)
        values=sorted(set(children['true']['values']+children['false']['values']))
        if len(values)>K.MAX_SUPPORT or any(abs(v)>K.MAX_LABEL for v in values):raise ValueError('cell union budget')
        return dict(kind='split',selector=selector,values=values,**children)
    proof=walk(root,ctx)
    cert=dict(schema=K.SCHEMA,minimum_width=2,source_hash=digest(expr),guards_hash=digest(guards),view_hash=digest(root),context_hash=digest(ctx),proof=proof,values=proof['values'])
    stats=dict(nodes=0,rows=0,joins=0,carriers=0)
    def count(e,g,c):
        stats['nodes']+=1
        if c['kind']=='split':
            for truth,key in [(True,'true'),(False,'false')]:
                nxt,ng=branch(e,g,c['selector'],truth);count(nxt,ng,c[key])
        else:
            _,s=K.check_leaf(e,g,c)
            for key in ['rows','joins','carriers']:stats[key]+=s[key]
    count(root,ctx,proof);cert['stats']=stats;K.verify(expr,guards,cert)
    return cert
