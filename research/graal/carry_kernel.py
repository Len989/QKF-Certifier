"""Paper-I forced rows and a source-phase quotient for mask successor gluing."""
import hashlib,json
REL=(0,1)
PHASES=((False,0),(True,0),(True,1))
MASKS=((0,0),(0,1),(1,1))
ALPHABET=tuple((m,a,g,x) for m,a in MASKS for g in range(m,a+1) for x in range(m,a+1))
START=(1,0,0,0,True,True,False)
SCHEMA='qkf-lower-carry-closure-v1'

def require(p,s):
    if not p:raise ValueError(s)
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def cmp(a,b):return (a>b)-(a<b)

def source_cell(program,phase,m,a,g):
    """One real ascending-loop cell, with incoming arithmetic carry exposed.
    Instructions are extracted from the source and executed on this cell.
    Before the first optional bit no physical carry exists.
    """
    incremented,carry=phase
    total=g+carry;bit=total&1;outcarry=total>>1
    optional=a and not m
    if incremented:
        if m and not bit:
            if program['mandatory_action'] in {'or','add'}:bit=1
            elif program['mandatory_action']=='skip':pass
            else:raise ValueError('unknown mandatory action')
        if not a and bit:
            if program['forbidden_action']=='add':outcarry+=1;bit=0
            elif program['forbidden_action']=='clear':bit=0
            elif program['forbidden_action']=='skip':pass
            else:raise ValueError('unknown forbidden action')
    elif optional:
        if program['first_action']=='add':outcarry+=bit;bit^=1
        elif program['first_action']=='or':bit=1
        else:raise ValueError('unknown first action')
        incremented=True
    require(outcarry in (0,1),'one-bit native carry budget')
    return bit,(incremented,outcarry)

def quotient(phase):return 1 if phase==(False,0) else phase[1]

def source_quotient(program):
    rows=[];cells={}
    for m,a in MASKS:
        for g in range(m,a+1):
            for phase in PHASES:
                y,nextphase=source_cell(program,phase,m,a,g)
                require(nextphase in PHASES and m<=y<=a,'source preserves every fixed mask cell')
                key=(m,a,g,quotient(phase));value=(y,quotient(nextphase))
                require(key not in cells or cells[key]==value,'source phase quotient is a congruence for output and continuation')
                cells[key]=value
                rows.append(dict(mask=[m,a],input=g,phase=list(phase),output=y,next_phase=list(nextphase),quotient=quotient(phase),next_quotient=quotient(nextphase)))
    return rows,cells

def labels():return [(m,a,g,y) for m,a in MASKS for g in range(m,a+1) for y in (0,1)]
def atom(cells,label,next_carry):
    m,a,g,y=label
    return sum(1<<c for c in REL if cells[m,a,g,c]==(y,next_carry))

def replay_rows(program,bridge,proofs):
    expected,cells=source_quotient(program);require(bridge==expected,'complete source-cell quotient binding')
    require(len(proofs)==len(labels()),'complete successor row family');tables={}
    for label,c in zip(labels(),proofs):
        require(set(c)=={'label','supplied','steps','table','kernel'} and c['label']==list(label),'row source label')
        supplied=[[1,atom(cells,label,0)],[2,atom(cells,label,1)]]
        require(c['supplied']==supplied,'native atom cells');values=dict(supplied)
        require(len(c['steps'])==2,'finite forced row derivation')
        for s in c['steps']:
            require(set(s)=={'operation','left','right','input','output'},'forced step fields')
            op=s['operation'];a=s['left'];b=s['right']
            require(op in {'union','intersection'} and a in values and b in values,'known row premises')
            source=a|b if op=='union' else a&b;image=values[a]|values[b] if op=='union' else values[a]&values[b]
            require(source not in values and s['input']==source and s['output']==image,'forced image');values[source]=image
        require(set(values)==set(range(4)),'full forced carrier domain')
        table=[values[i] for i in range(4)]
        require(c['table']==table,'completed row table')
        for a in range(4):
            for b in range(4):require(table[a|b]==table[a]|table[b] and table[a&b]==table[a]&table[b],'ground union/intersection homomorphism')
        require(c['kernel']==[[i for i in range(4) if table[i]==v] for v in sorted(set(table))],'row kernel')
        tables[label]=table
    return tables

def transition(q,col,rows):
    carry,gx,yx,gy,gmax,ymin,seen=q;m,a,g,x=col
    choices=[(y,c) for y in (0,1) for c in REL if rows[m,a,g,y][1<<c] & (1<<carry)]
    require(len(choices)==1,'unique glued source continuation')
    y,c=choices[0]
    return (c,cmp(g,x) or gx,cmp(y,x) or yx,cmp(g,y) or gy,gmax and g==a,ymin and y==m,seen or m!=a)

def boundaries(q):
    carry,gx,yx,gy,gmax,ymin,seen=q;result=[]
    for ms,ys in MASKS:
        for xs in range(ms,ys+1):
            gs=ys;ts=gs^carry
            order_gx=cmp(1-gs,1-xs) or gx
            order_tx=cmp(1-ts,1-xs) or yx
            order_gt=cmp(1-gs,1-ts) or gy
            typed=not(carry and gs==0)
            member=ms<=ts<=ys and typed
            bad=(carry==1 and not(gmax and ymin)) or (order_gx<0 and not(member and order_gt<0 and order_tx<=0))
            result.append(dict(sign_mask=[ms,ys],candidate_sign=xs,input_below_candidate=order_gx<0,
                               output_member=member,input_below_output=order_gt<0,output_below_candidate=order_tx<=0,
                               wrap_to_mask_minimum=bool(carry and gmax and ymin),bad=bool(bad)))
    return result

CONCLUSION=dict(widths='all positive mathematical word widths',
    theorem='For every mask word x greater than g in the minimum-sign slice, the successor t is a typed mask word and g < t <= x; overflow wraps nonsign bits to their mask minimum.',
    source_scope='The real ascending loop when at least one nonsign optional bit exists; virtual no-optional extension is used only in the induction, not substituted for the source zero branch.',
    induction='empty nonsign suffix, all mask/input/candidate columns, then every allowed sign column')

def replay(program,c):
    require(set(c)=={'schema','program','source_quotient','rows','states','initial','edges','boundaries','conclusion'},'carry certificate fields')
    require(c['schema']==SCHEMA and c['program']==program,'carry source binding')
    rows=replay_rows(program,c['source_quotient'],c['rows']);states=[tuple(q) for q in c['states']]
    require(states and len(states)<=432 and len(states)==len(set(states)),'finite successor carrier')
    for q in states:
        require(len(q)==7 and type(q[0]) is int and q[0] in REL and all(type(t) is int and t in (-1,0,1) for t in q[1:4]) and all(type(b) is bool for b in q[4:]),'successor observation type')
    require(type(c['initial']) is int and 0<=c['initial']<len(states) and states[c['initial']]==START,'empty word obligation')
    require(len(c['edges'])==len(states)==len(c['boundaries']),'complete successor obligations')
    for i,q in enumerate(states):
        require(len(c['edges'][i])==len(ALPHABET),'all successor bit columns')
        for col,j in zip(ALPHABET,c['edges'][i]):require(type(j) is int and 0<=j<len(states) and states[j]==transition(q,col,rows),'closed successor observation carrier')
        ends=boundaries(q);require(c['boundaries'][i]==ends and not any(e['bad'] for e in ends),'universal signed successor obligation')
    require(c['conclusion']==CONCLUSION,'successor theorem binding')
    return dict(status='proved_universal_mask_successor',states=len(states),columns=len(ALPHABET),transitions=len(states)*len(ALPHABET),sign_boundaries=4*len(states),source_phase_states=3,phase_quotient_classes=2,
                native_row_templates=len(rows),protected_carrier_size=4,forced_row_domain=4,row_kernel_classes=sorted({len(r['kernel']) for r in c['rows']}),central_carrier_quotient='diagonal')
