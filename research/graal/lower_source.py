"""Restricted, alpha-invariant bridge for the actual Graal lower helper.

The complete control/mask/iteration skeleton is checked. The first-pass
comparison and three repair actions are extracted and subsequently proved,
not inferred from the helper name. Native CodeUtil/mask primitives remain a
reviewed trust boundary, as in the preceding stage.
"""
import hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'previous'))
from source_contract import Parser as UpperParser,normal,COMPARISONS
from native_java import block_end
from carry_kernel import require,digest

class Parser(UpperParser):
    def statement(self):
        if self.i+1<len(self.tokens) and self.tokens[self.i+1]=='+=':
            name=self.take();self.take('+=');value=self.expression();self.take(';');return ('add_assign',name,value)
        if self.peek()=='GraalError':
            self.take();self.take('.');self.take('guarantee');self.take('(');condition=self.expression();self.take(',');message=self.take()
            require(message.startswith('"'),'literal guarantee message');self.take(')');self.take(';');return ('guarantee',condition,message)
        return super().statement()

def parsed(source):
    matches=list(re.finditer(r'private\s+static\s+long\s+computeLowerBound\s*\(([^)]*)\)\s*\{',source))
    require(len(matches)==1,'unique lower helper');m=matches[0];begin=source.index('{',m.start());end=block_end(source,begin)
    parameters=re.findall(r'\b(int|long|boolean)\s+(\w+)',m.group(1))
    require([t for t,n in parameters]==['int','long','long','long','boolean'],'typed lower parameters')
    ast=Parser(source[begin:end]).parse();aliases=dict(zip([n for t,n in parameters],['bits','bound','must','may','can_zero']))
    def collect(n):
        if not isinstance(n,tuple):return
        if n and n[0] in {'declare','for'}:
            name=n[2] if n[0]=='declare' else n[1]
            if name not in aliases:aliases[name]='v'+str(len(aliases)-5)
        for x in n:collect(x)
    collect(ast)
    def rename(n):
        if not isinstance(n,tuple):return n
        if n and n[0]=='name':return ('name',aliases.get(n[1],n[1]))
        if n and n[0]=='declare':return ('declare',n[1],aliases[n[2]],rename(n[3]))
        if n and n[0] in {'assign','add_assign','or_assign'}:return (n[0],aliases[n[1]],rename(n[2]))
        if n and n[0]=='for':return ('for',aliases[n[1]],rename(n[2]),rename(n[3]),aliases[n[4]],n[5],rename(n[6]))
        if n and n[0]=='binary' and n[1] in {'>','>='}:return ('binary','<' if n[1]=='>' else '<=',rename(n[3]),rename(n[2]))
        return tuple(rename(x) for x in n)
    return normal(rename(ast),{}),hashlib.sha256(source[begin:end].encode()).hexdigest()

def walk(node,path=()):
    if isinstance(node,tuple):
        yield path,node
        for i,x in enumerate(node):yield from walk(x,path+(i,))
def put(node,path,value):
    if not path:return value
    a=list(node);a[path[0]]=put(a[path[0]],path[1:],value);return tuple(a)

def compile_source(source):
    ast,body_hash=parsed(source)
    expected,_=parsed((ROOT/'LOWER_SHAPE.java').read_text())
    expected_loops=[(p,n) for p,n in walk(expected) if n and n[0]=='for']
    require(len(expected_loops)==2,'bridge skeleton loops')
    actual=dict(walk(ast));path,loop=expected_loops[0]
    require(path in actual and actual[path][0]=='for','descending source loop')
    # Only the comparison between newLowerBound + bit and lowerBound can vary.
    cp,canonical=next((p,n) for p,n in walk(loop) if n and n[0]=='binary' and n[1]=='<=' and n[3]==('name','bound'))
    guardnode=actual.get(path+cp);require(guardnode is not None and guardnode[0]=='binary' and guardnode[1] in COMPARISONS,'compiled first-pass comparison')
    # Normalization orients >/>= to </<= and reverses their operands.
    if guardnode[2:]==canonical[2:]:relations=COMPARISONS[guardnode[1]]
    elif guardnode[2:]==canonical[2:][::-1]:relations=sorted(-r for r in COMPARISONS[guardnode[1]])
    else:raise ValueError('first-pass comparison operands')
    normalized=put(ast,path+cp,canonical)
    second_path,second=expected_loops[1]
    actions=[(p,n) for p,n in walk(second) if n and n[0] in {'or_assign','add_assign'}]
    require(len(actions)==3,'three source carry repairs');program={}
    for role,(p,n) in zip(['mandatory_action','forbidden_action','first_action'],actions):
        candidate=actual.get(second_path+p);require(candidate is not None and candidate[0] in {'or_assign','add_assign'},'compiled native repair action')
        require(candidate[1:]==n[1:],'source repair operands')
        program[role]='or' if candidate[0]=='or_assign' else 'add'
        normalized=put(normalized,second_path+p,n)
    require(normalized==expected,'complete lower source shape, masks, directions, guards, zero handling and returns')
    bindings={};manifest=json.loads((ROOT/'previous/baseline/native/MANIFEST.json').read_text())
    for r in manifest['extracted']:
        if not r['name'].startswith('helper_') or r['name']=='helper_15':continue
        text=(ROOT/'previous/baseline/native'/(r['name']+'.inc')).read_text().rstrip('\n');declaration=text[:text.index('{')]
        start=source.find(declaration);require(start>=0,'native declaration '+r['name']);end=block_end(source,source.index('{',start))
        h=hashlib.sha256(source[start:end].encode()).hexdigest();require(h==r['sha256'],'native helper '+r['name']);bindings[r['name']]=h
    optional_branch=[['sweep'],['guarantee_le_bound'],['if_below_bound',[['successor']]]]
    adjust=[['if_no_optional',[['zero']],optional_branch]]
    ir=[['minimum'],['if_below_bound',adjust],['exclude_zero'],['if_below_bound',[['maximum_sentinel']]],['return']]
    return dict(source_sha256=hashlib.sha256(source.encode()).hexdigest(),body_sha256=body_hash,parsed_body_sha256=digest(ast),
                skeleton_sha256=digest(expected),native_helpers=bindings,
                sweep_guard=['and',['optional'],['comparison',relations]],carry_program=program,
                first_pass_bridge='Each optional nonsign bit is initially zero and visited once from high to low: source + bit equals | bit, with no signed overflow in the selected sign slice.',
                outer_ir=ir,
                native_widths=list(range(1,65)),mathematical_lift='same signed word and carry semantics; host-64-only zero branches are used only through their proved monotonic/nonempty native contracts')
