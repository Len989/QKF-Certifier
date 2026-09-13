"""All weak order types of seven named values check the exact upper-control IR."""
import hashlib,json
from row_kernel import compare,require

NAMES=['zero','must','minimum','negative_maximum','bound','raw','candidate']


def order_types(size):
    """Every total preorder exactly once, including every possible equality."""
    if size==1:
        yield (0,);return
    for old in order_types(size-1):
        count=max(old)+1
        for rank in range(count):yield old+(rank,)
        for rank in range(count+1):yield tuple(x+int(x>=rank) for x in old)+(rank,)


def execute(ir,ranks,may_sign,can_zero,sweep_value=None):
    env={};calls=[];path=[];returned=[]
    def expr(e):
        tag=e[0]
        if tag=='rank':
            name=e[1]
            member=name in {'must','minimum'} or name=='negative_maximum' and bool(may_sign)
            return ('value',ranks[name],member)
        if tag=='local':require(e[1] in env,'initialized order local');return env[e[1]]
        if tag=='may_sign':return bool(may_sign)
        if tag=='can_zero':return can_zero
        if tag=='boolean':return e[1]
        if tag=='empty_sentinel':return ('empty',None,False)
        if tag=='sweep':
            initial=expr(e[1]);require(initial[0]=='value' and initial[2],'sweep starts in the mask carrier')
            calls.append(initial[1]);return ('value',ranks['raw'] if sweep_value is None else sweep_value(initial[1]),True)
        if tag=='compare':
            a,b=expr(e[2]),expr(e[3]);require(a[0]==b[0]=='value','word order operands')
            return compare(a[1],b[1]) in e[1]
        if tag=='not':
            a=expr(e[1]);require(type(a) is bool,'Boolean operand');return not a
        require(tag in {'and','or'},'order control expression')
        a=expr(e[1]);b=expr(e[2]);require(type(a) is type(b) is bool,'Boolean operands')
        return a and b if tag=='and' else a or b
    def stmt(s):
        if returned:return
        tag=s[0]
        if tag=='block':
            for child in s[1]:stmt(child)
        elif tag=='assign':env[s[1]]=expr(s[2])
        elif tag=='if':
            decision=expr(s[1]);require(type(decision) is bool,'Boolean branch');path.append(decision)
            stmt(s[2] if decision else s[3])
        else:
            require(tag=='return','order control statement');returned.append(expr(s[1]))
    stmt(ir)
    require(len(returned)==1 and len(calls)==1,'one complete source return and one sweep')
    return returned[0],calls[0],path


def membership_bounds(value,r,kind):
    z,m,l,n=r['zero'],r['must'],r['minimum'],r['negative_maximum']
    if kind=='positive_only':return value>=m
    if kind=='negative_only':return l<=value<=n
    return l<=value<=n if value<z else value>=m


def mask_shape(r,kind):
    z,m,l,n=r['zero'],r['must'],r['minimum'],r['negative_maximum']
    if kind=='positive_only':return m>=z and l==m and n==z
    if kind=='negative_only':return l==m<=n<z
    return l<=n<z<=m


def evaluate(ir,record_cases=False):
    counts={};seen=0;admitted=0;hasher=hashlib.sha256();cases=[]
    for order in order_types(7):
        seen+=1;r=dict(zip(NAMES,order));z,u,x,y=r['zero'],r['bound'],r['candidate'],r['raw']
        for kind in ['positive_only','mixed','negative_only']:
            if not mask_shape(r,kind) or not membership_bounds(x,r,kind) or not membership_bounds(y,r,kind):continue
            for can_zero in [False,True]:
                result,initial,path=execute(ir,r,kind!='positive_only',can_zero)
                require(initial in {r['must'],r['minimum']},'source starts at a certified fixed-sign minimum')
                if (y<z)!=(initial<z) or y<initial:continue
                # Two instances of the universal sweep theorem: x=initial,
                # and x=the arbitrary concrete candidate of the final goal.
                if initial<=u and y>u:continue
                if (x<z)==(initial<z) and x<=u and x>y:continue
                admitted+=1;feasible=x<=u and (can_zero or x!=z)
                mode,value,member=result
                valid_value=mode=='value' and member and membership_bounds(value,r,kind) and value<=u and (can_zero or value!=z)
                error=(mode=='value' and not valid_value) or (feasible and (mode!='value' or x>value))
                case=dict(order=list(order),mask_kind=kind,can_zero=can_zero,initial=initial,
                          path=path,result=list(result),candidate_feasible=feasible)
                if error:return dict(status='counterexample',case=case,order_types_seen=seen)
                key=kind+' / zero='+str(can_zero)+' / '+mode
                counts[key]=counts.get(key,0)+1
                hasher.update((json.dumps(case,sort_keys=True,separators=(',',':'))+'\n').encode())
                if record_cases:cases.append(case)
    require(seen==47293 and admitted>0,'complete total-preorder universe')
    result=dict(status='proved_all_order_types',named_values=NAMES,total_preorders=seen,
                admitted_cases=admitted,branch_counts=counts,case_stream_sha256=hasher.hexdigest(),
                conclusion='Every value branch returns a feasible word. Every feasible candidate is <= the returned value. Every empty-sentinel branch has no feasible candidate.',
                transfer='Replacing the upper bound by this value, or returning empty on its proved empty branch, preserves intersection with any additional lower bound.')
    if record_cases:result['cases']=cases
    return result


def replay(ir,certificate):
    result=evaluate(ir)
    require(result['status']=='proved_all_order_types' and certificate==result,'complete universal order certificate')
    return result
