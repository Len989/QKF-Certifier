"""Restricted source compilation for two real Graal helpers, with native bindings.

The loop shape and mask construction are checked explicitly. Its decision
predicate is compiled, not assumed to be the desired <= comparison. The
outer helper becomes finite order/control IR that is executed by the kernel.
"""
import hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'baseline'))
from source_kernel import Parser as BaseParser
from native_java import block_end
from row_kernel import require,digest

COMPARISONS={'<':[-1],'<=':[-1,0],'==':[0],'!=':[-1,1],'>':[1],'>=':[0,1]}


class Parser(BaseParser):
    def statement(self):
        if self.peek()=='for':
            self.take();self.take('(');typ=self.take();name=self.take();self.take('=');initial=self.expression();self.take(';')
            condition=self.expression();self.take(';');target=self.take();step=self.take();self.take(step);self.take(')')
            require(typ=='int' and step in {'+','-'},'integer unit loop')
            return ('for',name,initial,condition,target,step,self.statement())
        if self.i+1<len(self.tokens) and self.tokens[self.i+1]=='|=':
            name=self.take();self.take('|=');value=self.expression();self.take(';');return ('or_assign',name,value)
        return super().statement()


def method(source,name):
    matches=list(re.finditer(r'private\s+static\s+long\s+'+re.escape(name)+r'\s*\(([^)]*)\)\s*\{',source))
    require(len(matches)==1,'unique source helper: '+name)
    m=matches[0];start=source.index('{',m.start());end=block_end(source,start)
    parameters=re.findall(r'\b(int|long|boolean)\s+(\w+)',m.group(1))
    expected=['int','long','long','long','boolean' if name=='computeUpperBound' else 'long']
    require([t for t,n in parameters]==expected,'typed source helper interface')
    arguments=[n for t,n in parameters]
    body=source[start:end]
    return arguments,Parser(body).parse(),hashlib.sha256(body.encode()).hexdigest()


def normal(node,aliases):
    if not isinstance(node,tuple):return node
    if node and node[0]=='name':return ('name',aliases.get(node[1],node[1]))
    if node and node[0]=='binary' and node[1] in {'&','|','&&','||'}:
        op=node[1];parts=[]
        def collect(x):
            if isinstance(x,tuple) and x[:2]==('binary',op):collect(x[2]);collect(x[3])
            else:parts.append(normal(x,aliases))
        collect(node[2]);collect(node[3]);return ('commutative',op,tuple(sorted(parts,key=repr)))
    return tuple(normal(x,aliases) for x in node)


def expression(text):
    p=Parser(text);node=p.expression();require(p.peek() is None,'template expression');return normal(node,{})


def native_bindings(source):
    manifest=json.loads((ROOT/'baseline/native/MANIFEST.json').read_text());bindings={}
    for r in manifest['extracted']:
        if not r['name'].startswith('helper_') or r['name'] in {'helper_13','helper_14'}:continue
        original=(ROOT/'baseline/native'/(r['name']+'.inc')).read_text().rstrip('\n')
        declaration=original[:original.index('{')];start=source.find(declaration)
        require(start>=0,'native helper declaration: '+r['name'])
        end=block_end(source,source.index('{',start));h=hashlib.sha256(source[start:end].encode()).hexdigest()
        require(h==r['sha256'],'changed native helper: '+r['name']);bindings[r['name']]=h
    return dict(helpers=bindings,shims='Exact preceding CodeUtil/base-class native semantics; source bridge is restricted, not a formal Java compiler')


def compile_sweep(source):
    names,ast,body_hash=method(source,'setOptionalBits');require(len(names)==5,'sweep interface')
    aliases=dict(zip(names,['bits','bound','must','may','initial']))
    require(ast[0]=='block','sweep block');body=[s for s in ast[1] if s[0]!='assert_disabled']
    require(len(body)==4,'complete sweep body')
    optional,value,loop,ret=body
    require(optional[:2]==('declare','long') and value[:2]==('declare','long'),'sweep local types')
    require(normal(optional[3],aliases)==expression('may & ~must & CodeUtil.mask(bits - 1)'),'nonsign optional mask')
    aliases[optional[2]]='optional';require(normal(value[3],aliases)==expression('initial'),'sweep initial value')
    aliases[value[2]]='value'
    require(loop[0]=='for' and loop[1]==loop[4] and loop[5]=='-','descending source traversal')
    require(normal(loop[2],aliases)==expression('bits - 1'),'first source position')
    aliases[loop[1]]='position';condition=loop[3]
    require(condition[0]=='binary' and (
            (condition[1]=='>=' and normal(condition[2],aliases)==expression('position') and normal(condition[3],aliases)==expression('0')) or
            (condition[1]=='<=' and normal(condition[2],aliases)==expression('0') and normal(condition[3],aliases)==expression('position'))),'all source positions through zero')
    require(loop[6][0]=='block' and len(loop[6][1])==2,'complete source loop body')
    bit,branch=loop[6][1]
    require(bit[:2]==('declare','long') and normal(bit[3],aliases)==expression('1L << position'),'source one-bit action')
    aliases[bit[2]]='bit';require(branch[0]=='if' and branch[3]==('block',()),'source decision branch')
    update=branch[2]
    if update[0]=='block':require(len(update[1])==1,'one source update');update=update[1][0]
    require(update[0]=='or_assign' and aliases.get(update[1])=='value' and normal(update[2],aliases)==expression('bit'),'source set-bit update')
    require(ret[0]=='return' and normal(ret[1],aliases)==expression('value'),'whole source return')
    def guard(node):
        tag=node[0]
        if tag=='unary' and node[1]=='!':return ['not',guard(node[2])]
        require(tag=='binary','supported source decision')
        op=node[1]
        if op in {'&&','||'}:return ['and' if op=='&&' else 'or',guard(node[2]),guard(node[3])]
        a,b=normal(node[2],aliases),normal(node[3],aliases)
        if op in {'!=','=='} and {repr(a),repr(b)}=={repr(expression('bit & optional')),repr(expression('0'))}:
            return ['optional'] if op=='!=' else ['not',['optional']]
        require(op in COMPARISONS,'source comparison')
        if a==expression('value | bit') and b==expression('bound'):return ['comparison',COMPARISONS[op]]
        if b==expression('value | bit') and a==expression('bound'):return ['comparison',sorted(-x for x in COMPARISONS[op])]
        raise ValueError('unsupported decision operands')
    return dict(guard=guard(branch[1]),body_sha256=body_hash,parsed_body_sha256=digest(ast),
                traversal='bits-1 down to 0; sign is fixed by optional mask',initial='mask minimum within chosen sign')


def compile_upper(source):
    names,ast,body_hash=method(source,'computeUpperBound');require(len(names)==5,'upper helper interface')
    aliases=dict(zip(names,['bits','bound','must','may','can_zero']));locals_={}
    def same(node,text):return normal(node,aliases)==expression(text)
    def expr(node):
        kind=node[0]
        if kind=='number':require(node[1]==0,'only order zero literal');return ['rank','zero']
        if kind=='boolean':return ['boolean',node[1]]
        if kind=='name':
            if node[1] in locals_:return ['local',locals_[node[1]]]
            role=aliases.get(node[1]);require(role in {'bound','can_zero'},'unsupported direct native word')
            return ['rank','bound'] if role=='bound' else ['can_zero']
        if kind=='unary':require(node[1]=='!','upper boolean negation');return ['not',expr(node[2])]
        if kind=='binary':
            op=node[1]
            if op in {'&&','||'}:return ['and' if op=='&&' else 'or',expr(node[2]),expr(node[3])]
            require(op in COMPARISONS,'upper order predicate');a,b=expr(node[2]),expr(node[3])
            if a==['may_sign'] or b==['may_sign']:
                other=b if a==['may_sign'] else a
                require(other==['rank','zero'] and op in {'==','!='},'native sign predicate')
                return ['not',['may_sign']] if op=='==' else ['may_sign']
            return ['compare',COMPARISONS[op],a,b]
        require(kind=='call','upper source expression')
        fn,args=node[1],node[2]
        if fn==('field',('name','CodeUtil'),'signExtend'):
            require(len(args)==2 and same(args[0],'must') and same(args[1],'bits'),'sign-extension interface');return ['rank','must']
        if fn==('field',('name','CodeUtil'),'minValue'):
            require(len(args)==1 and same(args[0],'bits'),'source empty sentinel');return ['empty_sentinel']
        require(fn[0]=='name','upper native callee');name=fn[1]
        if name=='minValueForMasks':
            require(len(args)==3 and all(same(a,b) for a,b in zip(args,['bits','must','may'])),'mask minimum interface');return ['rank','minimum']
        if name=='maxValueForMasks':
            require(len(args)==3 and all(same(a,b) for a,b in zip(args,['bits','must | (1L << bits - 1)','may'])),'negative maximum interface');return ['rank','negative_maximum']
        if name=='significantBit':
            require(len(args)==2 and same(args[0],'bits') and same(args[1],'may'),'may sign interface');return ['may_sign']
        if name=='setOptionalBits':
            require(len(args)==5 and all(same(a,b) for a,b in zip(args[:4],['bits','bound','must','may'])),'sweep source interface');return ['sweep',expr(args[4])]
        raise ValueError('unsupported native callee: '+name)
    def stmt(node):
        tag=node[0]
        if tag=='block':return ['block',[stmt(s) for s in node[1]]]
        if tag=='assert_disabled':return ['block',[]]
        if tag=='declare':
            require(node[1]=='long' and node[2] not in locals_ and node[2] not in aliases,'upper local declaration')
            value=expr(node[3]);locals_[node[2]]='v'+str(len(locals_));return ['assign',locals_[node[2]],value]
        if tag=='assign':require(node[1] in locals_,'declared local assignment');return ['assign',locals_[node[1]],expr(node[2])]
        if tag=='if':return ['if',expr(node[1]),stmt(node[2]),stmt(node[3])]
        if tag=='return':return ['return',expr(node[1])]
        raise ValueError('unsupported upper statement: '+tag)
    ir=stmt(ast)
    require(len(locals_)<=8,'source local budget')
    return dict(ir=ir,body_sha256=body_hash,parsed_body_sha256=digest(ast))


def compile_source(source):
    return dict(source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                native_bindings=native_bindings(source),sweep=compile_sweep(source),upper=compile_upper(source))
