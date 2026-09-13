"""Check source-derived observation rows and their compatible gluing.

The checker follows supplied paths and finite tables; it performs no path
search, candidate search, SMT call or general semantic-equivalence test.
"""
import itertools,json
from regular_interfaces import tree,order
from qkf_certifier.kernel import digest
from semantic_view import view,context,source_view,branch,literal,TRUE,FALSE

SCHEMA='qkf-semantic-observation-row-v1'
MAX_NODES=127;MAX_ROWS=256;MAX_SUPPORT=8;MAX_LABEL=7
OPS={'add','sub','mul','and','or','xor','not'}


def edges(guards):
    out=[]
    for i,(p,t) in enumerate(guards):
        if p[0]=='cmp0' and t:
            for kind in ['eq','u','s']:
                out.extend([dict(kind=kind,a=p[1],b=p[2],strict=0,guard=i),dict(kind=kind,a=p[2],b=p[1],strict=0,guard=i)])
        elif p[0] in {'cmp6','cmp2'}:
            a,b=p[1:] if t else (p[2],p[1]);out.append(dict(kind='u' if p[0]=='cmp6' else 's',a=a,b=b,strict=int(t),guard=i))
    return out


def path_fact(es,kind,start,end,path):
    if not isinstance(path,list) or len(path)>256:raise ValueError('order path budget')
    current=start;delta=0
    for i in path:
        if type(i) is not int or not 0<=i<len(es):raise ValueError('order edge index')
        e=es[i]
        if e['kind']!=kind or e['a']!=current:raise ValueError('order path continuity')
        current=e['b'];delta+=e['strict']
    if current!=end:raise ValueError('order path endpoint')
    return delta


def cut_value(term,kind):
    k=literal(term)
    if k is None:return None
    if kind=='u' and 0<=k<=3:return k
    if kind=='s' and -2<=k<=1:return k
    return None


def check_impossible(guards,proof):
    if proof['rule']=='false-guard':
        i=proof['guard'];p,t=guards[i]
        if not ((p==TRUE and not t) or (p==FALSE and t)):raise ValueError('guard is not false')
        return
    es=edges(guards);kind=proof['kind'];a=tree(proof['a']);b=tree(proof['b']);delta=path_fact(es,kind,a,b,proof['path'])
    if proof['rule']=='strict-cycle':
        if a!=b or delta<=0:raise ValueError('no strict order cycle')
    elif proof['rule']=='constant-order-conflict':
        x,y=cut_value(a,kind),cut_value(b,kind)
        if x is None or y is None or x+delta<=y:raise ValueError('compatible constant order')
    elif proof['rule']=='unsigned-below-zero':
        k=cut_value(b,'u')
        if kind!='u' or k is None or k-delta>=0:raise ValueError('not below unsigned zero')
    else:raise ValueError('impossibility rule')


def carrier_values(term,guards,proof):
    es=edges(guards);rule=proof['rule']
    if rule=='equal-literal':
        end=tree(proof['literal']);k=literal(end)
        if k is None or abs(k)>MAX_LABEL:raise ValueError('literal observation budget')
        path_fact(es,'eq',term,end,proof['path']);return [k]
    if rule=='constant-bit-mask':
        if term[0]!='and':raise ValueError('mask consumer')
        side=proof['side'];k=literal(term[side])
        if side not in (1,2) or k is None or not 0<=k<=3:raise ValueError('small mask')
        return [i for i in range(k+1) if i&~k==0]
    if rule!='order-interval':raise ValueError('carrier premise')
    kind=proof['kind'];upper=proof['upper'];end=tree(upper['constant']);hi=cut_value(end,kind)
    if hi is None:raise ValueError('unsafe upper cut at width two')
    hi-=path_fact(es,kind,term,end,upper['path'])
    if proof['lower'] is None:
        if kind!='u':raise ValueError('signed lower bound missing')
        lo=0
    else:
        lower=proof['lower'];start=tree(lower['constant']);lo=cut_value(start,kind)
        if lo is None:raise ValueError('unsafe lower cut at width two')
        lo+=path_fact(es,kind,start,term,lower['path'])
    if lo>hi or hi-lo+1>MAX_SUPPORT or max(abs(lo),abs(hi))>MAX_LABEL:raise ValueError('finite interval budget or empty interval')
    return list(range(lo,hi+1))


def glue_rows(expr,carriers):
    """Natural join over a single definition of each named value observation.

    All occurrences of one carrier reuse its same label convention. No label
    conversion across independent proofs can silently erase small-width aliases.
    """
    definitions={tree(c['term']):c for c in carriers};used=set();cache={};joins=0
    if len(definitions)!=len(carriers):raise ValueError('duplicate named carrier')
    def evaluate(e):
        nonlocal joins
        if e in cache:return cache[e]
        k=literal(e)
        if k is not None:rows=[((),k)]
        elif e in definitions:
            used.add(e);c=definitions[e];key=digest(e);rows=[(((key,k),),k) for k in c['values']]
        elif e[0] in OPS:
            children=[evaluate(x) for x in e[1:]];rows=set()
            for combination in itertools.product(*children):
                joins+=1
                if joins>10000:raise ValueError('observation join work budget')
                bindings={};compatible=True
                for binding,_ in combination:
                    for name,value in binding:
                        if name in bindings and bindings[name]!=value:compatible=False;break
                        bindings[name]=value
                if not compatible:continue
                xs=[value for _,value in combination];op=e[0]
                if op=='not':value=~xs[0]
                else:
                    a,b=xs;value={'add':lambda:a+b,'sub':lambda:a-b,'mul':lambda:a*b,'and':lambda:a&b,'or':lambda:a|b,'xor':lambda:a^b}[op]()
                if abs(value)>100000:raise ValueError('intermediate row label budget')
                rows.add((tuple(sorted(bindings.items())),value))
                if len(rows)>MAX_ROWS:raise ValueError('row cardinality budget')
            rows=sorted(rows)
        else:raise ValueError('missing finite carrier for '+e[0])
        cache[e]=rows;return rows
    rows=evaluate(expr)
    if used!=set(definitions):raise ValueError('unused carrier premise')
    return [dict(bindings=dict(bs),output=v) for bs,v in rows],joins


def cover(rows):
    values=sorted(set(r['output'] for r in rows))
    if len(values)>MAX_SUPPORT or any(abs(k)>MAX_LABEL for k in values):raise ValueError('output observation budget')
    return values


def check_leaf(expr,guards,c):
    if c['kind']=='impossible':check_impossible(guards,c['proof']);return [],dict(nodes=1,rows=0,joins=0,carriers=0)
    if c['kind']!='finite-row':raise ValueError('leaf kind')
    nodes=set(order(expr));carriers=c['carriers']
    if len(carriers)>16:raise ValueError('named carrier budget')
    for row in carriers:
        term=tree(row['term'])
        if term not in nodes:raise ValueError('carrier outside source-view query')
        values=carrier_values(term,guards,row['proof'])
        if values!=row['values']:raise ValueError('carrier coverage mismatch')
    rows,joins=glue_rows(expr,carriers)
    if rows!=c['rows']:raise ValueError('incompatible or missing observation rows')
    values=cover(rows)
    if c['values']!=values:raise ValueError('row quotient mismatch')
    return values,dict(nodes=1,rows=len(rows),joins=joins,carriers=len(carriers))


def verify(expr,guards,cert):
    if cert['schema']!=SCHEMA or cert['minimum_width']!=2 or cert['source_hash']!=digest(expr) or cert['guards_hash']!=digest(guards):raise ValueError('observation source/width binding')
    root,ctx=source_view(expr,guards)
    if cert['view_hash']!=digest(root) or cert['context_hash']!=digest(ctx):raise ValueError('native view binding')
    total=dict(nodes=0,rows=0,joins=0,carriers=0)
    def walk(e,g,c):
        total['nodes']+=1
        if total['nodes']>MAX_NODES:raise ValueError('observation proof tree budget')
        if c['kind']=='split':
            selector=tree(c['selector']);values=[]
            for truth,key in [(True,'true'),(False,'false')]:
                nxt,ng=branch(e,g,selector,truth);values+=walk(nxt,ng,c[key])
            out=sorted(set(values))
            if len(out)>MAX_SUPPORT or any(abs(k)>MAX_LABEL for k in out):raise ValueError('union cover budget')
        else:
            out,stats=check_leaf(e,g,c)
            for k in ['rows','joins','carriers']:total[k]+=stats[k]
        if c['values']!=out:raise ValueError('cell union mismatch')
        return out
    result=walk(root,ctx,cert['proof'])
    if result!=cert['values'] or total!=cert['stats']:raise ValueError('observation result accounting')
    return result,total
