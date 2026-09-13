"""Replay exact joint mask/range observations without search or word enumeration.

Trusted native bridges: signed-order key, aligned prefix cylinder, mask
intersection and removal of a named zero. The certificate supplies a complete
disjoint cover and an acyclic observation-union derivation, both checked here.
"""
import hashlib,json

SCHEMA='qkf-joint-carrier-certificate-v1'
MAX_WIDTH=4096


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def integer(v):return type(v) is int
def require(p,message):
    if not p:raise ValueError(message)


def validate_spec(spec):
    require(isinstance(spec,dict) and set(spec)=={'width','must','may','lower','upper','can_zero'},'joint specification fields')
    w=spec['width'];require(integer(w) and 1<=w<=MAX_WIDTH,'width budget')
    s=1<<(w-1);m=(1<<w)-1
    require(all(integer(spec[n]) for n in ['must','may','lower','upper']),'integer specification')
    require(0<=spec['must']<=m and 0<=spec['may']<=m,'mask width')
    require(-s<=spec['lower']<s and -s<=spec['upper']<s,'signed bounds')
    require(type(spec['can_zero']) is bool,'zero flag')
    return w,s,m


def empty():return dict(count=0,lower=None,upper=None,must=0,may=0,zero=False)


def keys(spec):
    w,s,m=validate_spec(spec);a,b=spec['must'],spec['may']
    # x -> x xor sign_bit turns signed word order into unsigned order.
    return (a&~s)|(~b&s),(b&~s)|(~a&s)


def cell(spec,start,free):
    """Exact image of one prefix cylinder intersected with the same word mask."""
    w,s,m=validate_spec(spec)
    require(integer(start) and integer(free) and 0<=free<=w,'prefix types')
    size=1<<free;require(0<=start<=m and start%size==0 and start+size<=m+1,'aligned prefix')
    km,ky=keys(spec);cm=km|start;cy=ky&(start+size-1)
    base=dict(start=start,free=free,must_key=cm,may_key=cy)
    if cm&~cy:return dict(**base,observation=empty())
    optional=cm^cy;n=optional.bit_count();has_zero=(s&cm)==cm and not(s&~cy)
    remove=has_zero and not spec['can_zero'];count=(1<<n)-int(remove)
    if not count:return dict(**base,observation=empty())
    low=cm;high=cy
    if remove and low==s:low+=optional&-optional
    if remove and high==s:high-=optional&-optional
    obs_m,obs_y=cm,cy
    if count==1:obs_m=obs_y=low
    must=(obs_m&~s)|(~obs_y&s);may=(obs_y&~s)|(~obs_m&s)
    observation=dict(count=count,lower=low-s,upper=high-s,must=must& m,may=may&m,
                     zero=has_zero and spec['can_zero'])
    return dict(**base,observation=observation)


def join(left,right):
    """Observation of a union; count additionally requires disjoint support."""
    if not left['count']:return dict(right)
    if not right['count']:return dict(left)
    return dict(count=left['count']+right['count'],lower=min(left['lower'],right['lower']),
                upper=max(left['upper'],right['upper']),must=left['must']&right['must'],
                may=left['may']|right['may'],zero=left['zero'] or right['zero'])


def image(observation,bit):
    if not observation['count']:return 0
    return int(not(observation['must']>>bit&1))|((observation['may']>>bit&1)<<1)


def cell_witness(spec,c,bit,value):
    """Construct one word for an already known nonempty observation cell."""
    if not(image(c['observation'],bit)&(1<<value)):return None
    w,s,m=validate_spec(spec);want=value^int(bit==w-1);mask=1<<bit
    cm,cy=c['must_key'],c['may_key'];key=cm|mask if want else cm
    require(not(cm&mask) or want,'witness fixed bit')
    if key==s and not spec['can_zero']:
        rest=(cy^cm)&~mask
        require(rest!=0,'missing nonzero witness');key^=rest&-rest
    return (key^s)&m


def member(spec,word):
    w,s,m=validate_spec(spec)
    if not integer(word) or not 0<=word<=m:return False
    value=word-(1<<w) if word&s else word
    return (spec['lower']<=value<=spec['upper'] and word&spec['must']==spec['must']
            and not word&~spec['may'] and (word!=0 or spec['can_zero']))


def answer(spec,query,observation,cells):
    require(isinstance(query,dict) and query.get('kind') in {'bit','summary','empty'},'query kind')
    kind=query['kind']
    if kind=='bit':
        require(set(query)=={'kind','index'} and integer(query['index']) and 0<=query['index']<spec['width'],'bit query')
        k=query['index'];support=image(observation,k);witnesses={}
        for value in [0,1]:
            if support&(1<<value):
                witnesses[str(value)]=next(word for c in cells if (word:=cell_witness(spec,c,k,value)) is not None)
        return dict(support=support,witnesses=witnesses)
    require(set(query)=={'kind'},'query fields')
    if kind=='empty':return dict(empty=observation['count']==0,witness=None if not observation['count'] else observation['lower']&((1<<spec['width'])-1))
    return dict(**observation,word=observation['must'] if observation['count']==1 else None)


def replay(spec,query,certificate):
    """The external caller supplies the expected source-bound specification."""
    w,s,m=validate_spec(spec);c=certificate
    require(isinstance(c,dict) and set(c)=={'schema','spec','query','binding','cells','joins','root','answer'},'certificate fields')
    require(c['schema']==SCHEMA and c['spec']==spec and c['query']==query,'source/query binding')
    require(c['binding']==digest([spec,query]),'source/query digest')
    cells=c['cells'];require(isinstance(cells,list) and len(cells)<=2*w+1,'cover budget')
    intrinsically_empty=spec['lower']>spec['upper'] or bool(spec['must']&~spec['may'])
    if intrinsically_empty:require(cells==[],'empty contract cover')
    position=spec['lower']+s
    for row in cells:
        require(isinstance(row,dict) and set(row)=={'start','free','must_key','may_key','observation'},'cell fields')
        require(row['start']==position,'cover gap, overlap or reordering')
        checked=cell(spec,row['start'],row['free']);require(row==checked,'native cell bridge')
        position+=1<<row['free']
    if not intrinsically_empty:require(position==spec['upper']+s+1,'incomplete interval cover')
    values=[r['observation'] for r in cells];supports=[{i} for i in range(len(cells))]
    require(isinstance(c['joins'],list) and len(c['joins'])==max(0,len(cells)-1),'union proof size')
    for node in c['joins']:
        require(isinstance(node,dict) and set(node)=={'left','right','observation'},'union node fields')
        a,b=node['left'],node['right']
        require(integer(a) and integer(b) and 0<=a<len(values) and 0<=b<len(values),'acyclic union premises')
        require(not supports[a]&supports[b],'duplicated union support')
        expected=join(values[a],values[b]);require(node['observation']==expected,'observation union')
        values.append(expected);supports.append(supports[a]|supports[b])
    if not cells:
        require(c['root'] is None and c['joins']==[],'empty proof root');observed=empty()
    else:
        root=c['root'];require(integer(root) and 0<=root<len(values),'proof root')
        require(supports[root]==set(range(len(cells))),'complete support at root');observed=values[root]
    expected=answer(spec,query,observed,cells);require(c['answer']==expected,'requested observation')
    if query['kind']=='bit':
        for b,x in expected['witnesses'].items():require(member(spec,x) and x>>query['index']&1==int(b),'word witness')
    return dict(status='proved_joint_observation',answer=expected,covered_cells=len(cells),
                represented_words=observed['count'],enumerated_words=0,proof_joins=len(c['joins']))
