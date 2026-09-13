"""Read the actual selected Java body and replay its complete mask observation.

This is a deliberately restricted source interpreter. It rejects unsupported
syntax/calls. Exact native helper bodies have separate reviewed contracts.
Every reachable create call consumes a scoped hull certificate; all remaining
source branches must have the same proved observable result.
"""
import hashlib,json,re
from dataclasses import dataclass,replace
from mask_terms import V,tree,cube,lo,hi,sign_rows,valid_table,word_ast
from hull_kernel import native_bindings,replay_hull
from native_java import block_end

SCHEMA='qkf-complete-source-mask-observation-v1'
CONTRACT='two nonbottom KnownBits pairs (Z,O), disjoint Z/O per input, one common positive width'


def plain(x):return json.loads(json.dumps(x))
def require(p,message):
    if not p:raise ValueError(message)


def body(source,operation):
    require(operation in {'and','or','xor','add','sub'},'selected operation')
    marker='new ArithmeticOpTable.BinaryOp.'+operation.capitalize()+'('
    start=source.index(marker);decl=source.index('protected Stamp foldStampImpl(',start)
    brace=source.index('{',decl);end=block_end(source,brace)
    signature=source[decl:brace]
    names=re.findall(r'\bStamp\s+([A-Za-z_]\w*)',signature[signature.index('('):])
    require(len(names)==2,'binary Stamp interface')
    return names,source[brace:end]


TOKEN=re.compile(r'\s+|//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\d+[lL]?|[A-Za-z_$][\w$]*|>>>|>>|<<|>=|<=|==|!=|&&|\|\||\|=|\+=|\S')
PRECEDENCE={'||':1,'&&':2,'|':3,'^':4,'&':5,'==':6,'!=':6,'<':7,'>':7,'<=':7,'>=':7,'<<':8,'>>':8,'>>>':8,'+':9,'-':9,'*':10,'/':10,'%':10}
TYPES={'Stamp','IntegerStamp','int','long','boolean'}


class Parser:
    def __init__(self,text):
        self.tokens=[m.group() for m in TOKEN.finditer(text) if not(m.group().isspace() or m.group().startswith(('//','/*')))];self.i=0
    def peek(self):return self.tokens[self.i] if self.i<len(self.tokens) else None
    def take(self,expected=None):
        t=self.peek();require(t is not None and (expected is None or t==expected),'Java token: expected '+repr(expected)+' got '+repr(t))
        self.i+=1;return t
    def expression(self,minimum=1):
        left=self.unary()
        while self.peek() in PRECEDENCE and PRECEDENCE[self.peek()]>=minimum:
            op=self.take();right=self.expression(PRECEDENCE[op]+1);left=('binary',op,left,right)
        return left
    def unary(self):
        if self.peek() in {'!','~','-','+'}:return ('unary',self.take(),self.unary())
        if self.peek()=='(' and self.i+2<len(self.tokens) and self.tokens[self.i+1] in TYPES and self.tokens[self.i+2]==')':
            self.take('(');typ=self.take();self.take(')');return ('cast',typ,self.unary())
        if self.peek()=='(':
            self.take();left=self.expression();self.take(')')
        else:
            name=self.take()
            if re.fullmatch(r'\d+[lL]?',name):left=('number',int(name.rstrip('lL')))
            elif name in {'true','false'}:left=('boolean',name=='true')
            else:require(bool(re.fullmatch(r'[A-Za-z_$][\w$]*',name)),'unsupported Java primary');left=('name',name)
        while self.peek() in {'.','('}:
            if self.peek()=='.':self.take();left=('field',left,self.take())
            else:
                self.take('(');args=[]
                if self.peek()!=')':
                    args.append(self.expression())
                    while self.peek()==',':self.take();args.append(self.expression())
                self.take(')');left=('call',left,tuple(args))
        return left
    def statement(self):
        t=self.peek()
        if t=='{':
            self.take();rows=[]
            while self.peek()!='}':rows.append(self.statement())
            self.take('}');return ('block',tuple(rows))
        if t=='if':
            self.take();self.take('(');condition=self.expression();self.take(')');yes=self.statement();no=('block',())
            if self.peek()=='else':self.take();no=self.statement()
            return ('if',condition,yes,no)
        if t=='return':self.take();value=self.expression();self.take(';');return ('return',value)
        if t=='assert':
            # The recorded Java execution uses -da. Parse through the complete statement.
            raw=[]
            while self.peek()!=';':raw.append(self.take())
            self.take(';');return ('assert_disabled',tuple(raw))
        if t=='final':self.take();t=self.peek()
        if t in TYPES:
            typ=self.take();name=self.take();self.take('=');value=self.expression();self.take(';');return ('declare',typ,name,value)
        left=self.expression()
        require(self.peek()=='=','unsupported Java statement');self.take('=');right=self.expression();self.take(';')
        require(left[0]=='name','only local assignment is supported');return ('assign',left[1],right)
    def parse(self):
        result=self.statement();require(self.peek() is None,'unconsumed Java body');return result


@dataclass(frozen=True)
class Stamp:
    carrier:tuple


@dataclass
class State:
    env:dict
    guards:tuple=()
    decisions:tuple=()
    result:Stamp|None=None


class Interpreter:
    def __init__(self,source,create_handler):
        self.source=source;self.create_handler=create_handler;self.calls=0
    def evaluate(self,node,state):
        kind=node[0];env=state.env
        if kind=='number':return ('int',node[1])
        if kind=='boolean':return node[1]
        if kind=='name':require(node[1] in env,'unbound Java local: '+node[1]);return env[node[1]]
        if kind=='cast':
            result=self.evaluate(node[2],state);require(node[1] in {'IntegerStamp','Stamp'} and isinstance(result,Stamp),'unsupported cast');return result
        if kind=='field':
            obj=self.evaluate(node[1],state);require(isinstance(obj,Stamp),'Stamp field owner');c=obj.carrier
            fields={'mustBeSet':c[1],'mayBeSet':c[2],'lowerBound':lo(c),'upperBound':hi(c)}
            require(node[2] in fields,'unsupported Stamp field');return fields[node[2]]
        if kind=='unary':
            x=self.evaluate(node[2],state)
            if node[1]=='~':return ('not',x)
            if node[1] in {'-','+'} and isinstance(x,tuple) and x[0]=='int':return ('int',x[1]*(-1 if node[1]=='-' else 1))
            if node[1]=='!' and type(x) is bool:return not x
            raise ValueError('unsupported unary source action')
        if kind=='binary':
            op=node[1];a,b=self.evaluate(node[2],state),self.evaluate(node[3],state)
            if op in {'&','|','^'}:return ({'&':'and','|':'or','^':'xor'}[op],a,b)
            if op in {'==','!=','<','<=','>','>='}:return (op,a,b)
            raise ValueError('unsupported binary source action: '+op)
        if kind=='call':
            fn=node[1];args=[self.evaluate(a,state) for a in node[2]]
            if fn[0]=='field' and fn[1]==('name','Math'):
                require(fn[2]=='min' and len(args)==2,'unsupported Math call');return ('min',*args)
            if fn[0]=='field':
                obj=self.evaluate(fn[1],state);require(isinstance(obj,Stamp) and args==[],'Stamp method receiver')
                if fn[2]=='isEmpty':valid_table(obj.carrier);return False
                if fn[2]=='getBits':return ('width',)
                raise ValueError('unsupported Stamp method: '+fn[2])
            require(fn[0]=='name','native callee syntax');name=fn[1]
            if name=='significantBit':require(len(args)==2 and args[0]==('width',),'significant bit width');return ('sign',args[1])
            if name in {'minValueForMasks','maxValueForMasks','stampForMask'}:
                require(len(args)==3 and args[0]==('width',),'mask helper interface');c=cube(args[1],args[2]);valid_table(c)
                if name=='minValueForMasks':return lo(c)
                if name=='maxValueForMasks':return hi(c)
                return Stamp(c)
            if name=='create':
                require(len(args) in {5,6} and args[0]==('width',),'create interface')
                c=cube(args[3],args[4]);zero=True if len(args)==5 else args[5]
                self.create_handler(self.calls,c,args[1],args[2],zero,state.guards)
                self.calls+=1;return Stamp(c)
            raise ValueError('unsupported native call: '+name)
        raise ValueError('unsupported source expression')
    def execute(self,node,states):
        kind=node[0]
        if kind=='block':
            for child in node[1]:states=self.execute(child,states)
            return states
        out=[]
        for state in states:
            if state.result is not None:out.append(state);continue
            if kind=='assert_disabled':out.append(state)
            elif kind in {'declare','assign'}:
                name=node[2] if kind=='declare' else node[1];value=node[3] if kind=='declare' else node[2]
                new=dict(state.env);new[name]=self.evaluate(value,state);out.append(replace(state,env=new))
            elif kind=='return':
                value=self.evaluate(node[1],state);require(isinstance(value,Stamp),'return is not a proved Stamp projection');out.append(replace(state,result=value))
            elif kind=='if':
                condition=self.evaluate(node[1],state)
                for truth,branch in [(True,node[2]),(False,node[3])]:
                    if type(condition) is bool:
                        if condition!=truth:continue
                        guards=state.guards
                    else:
                        guards=state.guards+((condition,truth),)
                        if not sign_rows(guards):continue
                    child=replace(state,env=dict(state.env),guards=guards,decisions=state.decisions+((condition,truth),))
                    out.extend(self.execute(branch,[child]))
            else:raise ValueError('unsupported source statement')
        return out


def observe_source(source,operation,create_handler):
    bindings=native_bindings(source);names,raw=body(source,operation);ast=Parser(raw).parse()
    a=cube(V[1],('not',V[0]));b=cube(V[3],('not',V[2]));valid_table(a);valid_table(b)
    interpreter=Interpreter(source,create_handler)
    terminal=interpreter.execute(ast,[State(dict(zip(names,[Stamp(a),Stamp(b)])))])
    require(terminal and all(s.result is not None for s in terminal),'complete return coverage')
    carriers=[s.result.carrier for s in terminal]
    require(all(c==carriers[0] for c in carriers),'source branches have different mask observations')
    c=carriers[0];expr=('pair',word_ast(('not',c[2])),word_ast(c[1]))
    leaves=[dict(guards=plain(s.guards),decisions=plain(s.decisions),carrier=plain(s.result.carrier)) for s in terminal]
    return dict(source_sha256=hashlib.sha256(source.encode()).hexdigest(),body_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                parsed_body_sha256=hashlib.sha256(json.dumps(ast).encode()).hexdigest(),native_bindings=bindings,
                leaves=leaves,create_calls=interpreter.calls,expression=plain(expr))


def replay_source(source,operation,certificate):
    c=certificate;require(isinstance(c,dict) and set(c)=={'schema','operation','contract','source_observation','hull_certificates'},'source certificate fields')
    require(c['schema']==SCHEMA and c['operation']==operation and c['contract']==CONTRACT,'source contract')
    proofs=c['hull_certificates'];require(isinstance(proofs,list) and len(proofs)<=64,'source proof budget')
    def handler(index,carrier,lower,upper,zero,guards):
        require(index<len(proofs),'missing source call certificate')
        replay_hull(source,carrier,lower,upper,zero,guards,proofs[index])
    observed=observe_source(source,operation,handler)
    require(observed['create_calls']==len(proofs),'unused source call certificate')
    require(observed==c['source_observation'],'complete source observation binding')
    return observed
