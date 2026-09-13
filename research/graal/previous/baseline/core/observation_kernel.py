"""Source-bound finite observations and checked run/carry gluing.

All new rules have minimum width 2. Whole programs retain the independent
original width-one obligation. Families are fixed; the producer selects within
them. This module performs no candidate search or SMT call.
"""
import itertools,json
from environment import ROOT
from qkf_certifier.kernel import at,replace,digest,Z,T,W
from regular_interfaces import tree,order
from symbolic_bridge import path_guards
import kernel as symbolic_kernel

SCHEMA='qkf-observation-choice-v1'
ONE=('const',1)
MAX_SUPPORT=8
NEGATE={0:1,1:0,6:9,7:8,8:7,9:6}
REVERSE={0:0,1:1,6:8,7:9,8:6,9:7}


def const(k):return Z if k==0 else T if k==-1 else ('const',k)


def literal(e):
    if e==Z:return 0
    if e==T:return -1
    if e[0]=='const' and abs(e[1])<=7:return e[1]
    return None


def support(e,guards,depth=0):
    """Checked finite cover, with guards taken only from the actual source path.

    A cover can contain unreachable values and is not claimed to be minimal.
    Width-independent signed integer labels denote their modular word literal.
    """
    if depth>8:raise ValueError('support depth')
    k=literal(e)
    if k is not None:return [k],dict(rule='literal',value=k)
    lo=0;hi=None;used=[]
    for i,(g,truth) in enumerate(guards):
        if g[0] not in {'cmp'+str(p) for p in NEGATE}:continue
        p=int(g[0][3:]);p=p if truth else NEGATE[p];a,b=g[1:]
        if b==e:a,b=b,a;p=REVERSE[p]
        c=literal(b)
        if a!=e or c is None or not 0<=c<=3:continue
        if p==0:lo=max(lo,c);hi=c if hi is None else min(hi,c)
        elif p in (6,7):bound=c-int(p==6);hi=bound if hi is None else min(hi,bound)
        elif p in (8,9):lo=max(lo,c+int(p==8))
        else:continue
        used.append(i)
    if hi is not None and 0<=lo<=hi<=3:
        return list(range(lo,hi+1)),dict(rule='unsigned-guard-cover',lower=lo,upper=hi,guards=used,minimum_width=2)
    op=e[0]
    if op=='select':
        a,pa=support(e[2],guards+[(e[1],True)],depth+1)
        b,pb=support(e[3],guards+[(e[1],False)],depth+1)
        values=sorted(set(a+b));proof=dict(rule='source-select-cover',true=pa,false=pb)
    elif op=='and' and any(literal(t) in (0,1,2,3) for t in e[1:]):
        side=next(i for i in (1,2) if literal(e[i]) in (0,1,2,3));mask=literal(e[side])
        values=[i for i in range(mask+1) if not i&~mask];proof=dict(rule='constant-mask-cover',side=side,mask=mask)
    elif op=='not':
        a,pa=support(e[1],guards,depth+1);values=sorted(set(~i for i in a));proof=dict(rule='complement-cover',premise=pa)
    elif op in {'add','sub','and','or','xor'}:
        a,pa=support(e[1],guards,depth+1);b,pb=support(e[2],guards,depth+1)
        fn={'add':lambda x,y:x+y,'sub':lambda x,y:x-y,'and':lambda x,y:x&y,'or':lambda x,y:x|y,'xor':lambda x,y:x^y}[op]
        values=sorted(set(fn(x,y) for x in a for y in b));proof=dict(rule='finite-native-operation-cover',op=op,left=pa,right=pb)
    else:raise ValueError('no finite support derivation')
    if len(values)>MAX_SUPPORT or any(abs(x)>7 for x in values):raise ValueError('finite support budget')
    return values,proof


def multiply_cell(x,k):
    if abs(k)>7:raise ValueError('small native multiplier cell')
    if k==0:return Z
    value=x
    for _ in range(abs(k)-1):value=('add',value,x)
    return ('sub',Z,value) if k<0 else value


def partition_cells(cells,observation):
    """Factor a supplied finite row; equal labels need a single output term.

    Obstructions concern this finite cover. They are not silently called
    counterexamples to the whole source program.
    """
    groups={}
    for label,value in cells:
        key=(label!=0) if observation=='zero' else label%2 if observation=='parity' else label
        if key in groups and groups[key]['value']!=value:
            return None,dict(kind='finite-row-obstruction',observation=observation,
                             labels=[groups[key]['labels'][0],label],
                             outputs=[groups[key]['value'],value],
                             scope='supplied action row over the derived cover; source reachability not asserted')
        groups.setdefault(key,dict(labels=[],value=value))['labels'].append(label)
    return list(groups.values()),None


def emit_row(arg,groups):
    out=groups[-1]['value']
    for g in reversed(groups[:-1]):
        predicates=[('cmp0',arg,const(k)) for k in g['labels']]
        test=predicates[0]
        for p in predicates[1:]:test=('boolor',test,p)
        out=('select',test,g['value'],out)
    return out


def finite_multiply(e,guards,side,observation):
    if e[0]!='mul' or side not in (1,2) or observation not in {'zero','parity','exact'}:raise ValueError('finite row parameters')
    values,derived=support(e[side],guards)
    other=e[3-side];cells=[(k,multiply_cell(other,k)) for k in values]
    groups,bad=partition_cells(cells,observation)
    if bad:raise ValueError(json.dumps(bad))
    proof=dict(kind='finite-multiplier-row',side=side,cover=values,cover_derivation=derived,
               supplied_cells=[dict(label=k,value=v) for k,v in cells],observation=observation,
               factor=groups,minimum_width=2)
    return emit_row(e[side],groups),proof


def joint_binary(e,guards):
    if e[0]!='mul':raise ValueError('joint consumer')
    a,pa=support(e[1],guards);b,pb=support(e[2],guards)
    if not set(a)<=set([0,1]) or not set(b)<=set([0,1]):raise ValueError('not a binary product carrier')
    cells=[dict(a=x,b=y,product=x*y,meet=x&y) for x,y in itertools.product(a,b)]
    if any(c['product']!=c['meet'] for c in cells):raise ValueError('finite carrier consistency')
    return ('and',e[1],e[2]),dict(kind='joint-binary-carrier',left_cover=a,right_cover=b,left=pa,right=pb,cells=cells,minimum_width=2)


def division_unit(e,merge):
    if e[0]!='sdiv' or e[1]!=ONE or type(merge) is not bool:raise ValueError('unit quotient family')
    d=e[2]
    # At w>=2, +1 is signed positive. All other nonzero nonunit divisors
    # have magnitude at least 2. The total-zero case is explicitly preserved.
    if merge:
        after=('select',('boolor',('cmp0',d,Z),('cmp0',d,T)),T,('select',('cmp0',d,ONE),ONE,Z))
        classes=[dict(inputs=['zero','minus_one'],output='ones'),dict(inputs=['one'],output='one'),dict(inputs=['rest'],output='zero')]
    else:
        after=('select',('cmp0',d,Z),T,('select',('cmp0',d,ONE),ONE,('select',('cmp0',d,T),T,Z)))
        classes=[dict(inputs=[i],output=o) for i,o in [('zero','ones'),('one','one'),('minus_one','ones'),('rest','zero')]]
    return after,dict(kind='signed-unit-row',minimum_width=2,
        cells=[['zero','ones'],['one','one'],['minus_one','ones'],['rest','zero']],
        rest_condition='signed magnitude >= 2',classes=classes,
        separation=dict(width=2,divisors=[0,1,2],outputs=[3,1,0]))


def simple(e):
    op=e[0]
    if op=='mul' and ONE in e[1:]:return (e[2] if e[1]==ONE else e[1]),'multiply-one'
    if op=='mul' and Z in e[1:]:return Z,'multiply-zero'
    if op=='sub' and e[1]==Z and e[2][0]=='sub':return ('sub',e[2][2],e[2][1]),'negative-difference-modular'
    sign=('set_sign_bit',Z);clear=('clear_sign_bit',T)
    if op in {'countl_zero','countl_one','countr_zero','countr_one'}:
        x=e[1]
        table={sign:{'countl_zero':Z,'countl_one':ONE,'countr_zero':('sub',W,ONE),'countr_one':Z},
               clear:{'countl_zero':ONE,'countl_one':Z,'countr_zero':Z,'countr_one':('sub',W,ONE)},
               ONE:{'countl_zero':('sub',W,ONE),'countl_one':Z,'countr_zero':Z,'countr_one':ONE}}
        if x in table:return table[x][op],'native-constant-run-minimum-width-two'
    raise ValueError('no supporting semantic bridge')


def boundary(e,representation):
    if not(e[0]=='shl' and e[1]==ONE and e[2][0] in {'countr_zero','countr_one'}):raise ValueError('low boundary family')
    count=e[2];x=count[1];desired=int(count[0].endswith('one'))
    if representation=='mask':
        L=('set_low_bits',Z,count)
        after=('and',('not',L),('or',('shl',L,ONE),ONE))
        data=json.loads((ROOT/'development/low_boundary_lemma.json').read_text())
        expected_source=dict(schema=symbolic_kernel.DSL,name='low_boundary_universal',inputs=[],parameters=['n'],
          assume=['and',['le',0,'n'],['le','n','w']],
          claims=[['word_eq',['shl',['lowmask',1],'n'],['and',['not',['lowmask','n']],['or',['shl',['lowmask','n'],1],['lowmask',1]]]]])
        if data['source']!=expected_source:raise ValueError('universal boundary source binding')
        proof=dict(kind='low-boundary-mask',source=expected_source,certificate=data['certificate'],
                   substitution=dict(n=count),count_range=[0,'w'],minimum_width=2)
    elif representation=='carry':
        after=('and',('not',x),('add',x,ONE)) if desired else ('and',x,('sub',Z,x))
        rows=[]
        for p,b in itertools.product((0,1),repeat=2):
            y=b if desired else 1-b;c=p
            boundary_bit=p&(1-y);sum_bit=y^c;result=(1-y)&sum_bit
            nxt=p&y;carry_next=y&c
            if result!=boundary_bit or nxt!=carry_next:raise ValueError('run/carry commutation')
            rows.append(dict(state=[p,c],input=b,boundary=boundary_bit,arithmetic=result,next=[nxt,carry_next]))
        proof=dict(kind='low-boundary-carry',desired=desired,initial=[1,1],relation=[[0,0],[1,1]],
                   transitions=rows,terminal='both end carries discarded',minimum_width=2,
                   native_bridges=['count-to-first-mismatch-bit','addition-carry-recurrence','complement-plus-one-is-modular-negation'])
    else:raise ValueError('boundary representation')
    return after,proof


def derive(initial,path,kind,parameter):
    e=at(initial,path);guards=path_guards(initial,path)
    if kind=='finite-row':after,proof=finite_multiply(e,guards,parameter['side'],parameter['observation'])
    elif kind=='joint-binary':after,proof=joint_binary(e,guards)
    elif kind=='unit-division':after,proof=division_unit(e,parameter['merge'])
    elif kind=='boundary':after,proof=boundary(e,parameter['representation'])
    elif kind=='supporting-bridge':
        after,name=simple(e);proof=dict(kind='supporting-semantic-bridge',name=name,minimum_width=2)
    else:raise ValueError('observation family')
    return after,proof,guards


def proof_steps(proof):
    if proof['kind']=='low-boundary-mask':
        return 1+symbolic_kernel.verify(proof['source'],proof['certificate'])['proof_nodes']
    if proof['kind']=='low-boundary-carry':return len(proof['transitions'])+len(proof['relation'])+1+len(proof['native_bridges'])
    # Count the complete finite derivation, including all guard/cover nodes.
    def nodes(p):return 1+sum(nodes(v) for v in p.values() if isinstance(v,dict)) if isinstance(p,dict) else 0
    return nodes(proof)+len(proof.get('supplied_cells',proof.get('cells',[])))+len(proof.get('factor',proof.get('classes',[])))


def replay(initial,trace,expected):
    if not isinstance(trace,list) or len(trace)>1000:raise ValueError('observation trace budget')
    root=initial;steps=0
    for t in trace:
        if t['schema']!=SCHEMA or t['minimum_width']!=2 or t['before_hash']!=digest(root):raise ValueError('observation binding')
        after,p,guards=derive(root,t['path'],t['kind'],t['parameter'])
        if digest(t['guards'])!=digest(guards) or digest(t['proof'])!=digest(p) or tree(t['after'])!=after:raise ValueError('observation derivation mismatch')
        steps+=proof_steps(p)
        root=replace(root,t['path'],after)
        if t['after_hash']!=digest(root):raise ValueError('observation result binding')
    if root!=tree(expected):raise ValueError('observation final expression')
    return root,steps
