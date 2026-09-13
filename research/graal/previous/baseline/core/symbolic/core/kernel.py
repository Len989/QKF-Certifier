"""Trusted symbolic bit observation compiler and certificate checker.

No untrusted search imports. Scalar arithmetic is mathematical integer
arithmetic; word widths are positive and logical shifts are totalized.
"""
from fractions import Fraction
import hashlib,json,math,sys

SCHEMA='qkf-transported-count-certificate-v3'
DSL='qkf-symbolic-bit-obligation-v1'
SEMANTICS='positive-width;integer-scalars;total-zero-invalid-shifts;transported-count-rows-v3'
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def tree(x):return tuple(map(tree,x)) if isinstance(x,(tuple,list)) else x
def lin(items):return tuple(sorted((k,int(v)) for k,v in dict(items).items() if v))
def const(n):return lin({'#':n})
def var(n):return ((n,1),)
def add(a,b):
    d=dict(a)
    for k,v in b:d[k]=d.get(k,0)+v
    return lin(d)
def scale(a,k):return lin({n:c*k for n,c in a})
def sub(a,b):return add(a,scale(b,-1))
W=var('w');I=var('i')
def Not(x):
    if isinstance(x,bool):return not x
    return x[1] if x[0]=='not' else ('not',x)
def And(*xs):
    result=set()
    for x in xs:
        if x is False:return False
        if x is True:continue
        result.update(x[1:] if x[0]=='and' else [x])
    if any(Not(x) in result for x in result):return False
    if not result:return True
    ordered=tuple(sorted(result,key=repr))
    return ordered[0] if len(ordered)==1 else ('and',*ordered)
def Or(*xs):return Not(And(*(Not(x) for x in xs)))
def Xor(a,b):return Or(And(a,Not(b)),And(Not(a),b))
def iff(a,b):return Not(Xor(a,b))
def imply(a,b):return Or(Not(a),b)
def le(a,b):
    d=sub(a,b);vs=[abs(c) for _,c in d]
    if not any(k!='#' for k,_ in d):return dict(d).get('#',0)<=0
    g=math.gcd(*vs) if vs else 1
    return ('le',lin({k:c//g for k,c in d}))
def lt(a,b):return le(add(a,const(1)),b)
def eq(a,b):return And(le(a,b),le(b,a))
def inrange(j):return And(le(const(0),j),lt(j,W))

class Unsupported(ValueError):pass
class Compiler:
    def __init__(self,source,interface_level=0):
        if type(interface_level) is not int or interface_level not in (0,1,2):raise ValueError('interface level')
        self.interface_level=interface_level;self.added_observations=[]
        if source.get('schema')!=DSL:raise ValueError('DSL schema')
        self.source=source;self.inputs=source['inputs'];self.parameters=source.get('parameters',[])
        names=self.inputs+self.parameters
        if len(set(names))!=len(names) or any(not isinstance(n,str) or not n.isidentifier() or n in {'w','i'} for n in names):raise ValueError('input/parameter names')
        self.counts={};self.view_counts={};self.transported_rows=[];self.view_constraints=[];self.transport_trace=[];self.bits=set();self.scalar_cache={};self.bit_cache={}
    def scalar(self,e):
        e=tree(e)
        if e in self.scalar_cache:return self.scalar_cache[e]
        if type(e) is int:r=[(True,const(e))]
        elif isinstance(e,str):
            if e!='w' and e not in self.parameters:raise Unsupported('scalar name '+e)
            r=[(True,var(e))]
        elif isinstance(e,tuple) and e[0] in {'clz','clo','ctz','cto'} and len(e)==2:
            from transport import action,transported_kind,pullback
            view=('input',e[1]) if isinstance(e[1],str) else e[1]
            bijection=action(view)
            if bijection is not None:
                name,reverse,flip=bijection
                if name not in self.inputs:raise Unsupported('base input name')
                base=(transported_kind(e[0],reverse,flip),name)
                if base not in self.counts:self.counts[base]='@n'+str(len(self.counts)+len(self.view_counts))
                if e!=base:self.transport_trace.append({'source':e,'base_count':base,'kind':'bijective-action'})
                r=[(True,var(self.counts[base]))]
            elif isinstance(view,tuple) and len(view)==2 and view[0] in {'not','reverse'}:
                inner=view;reverse=flip=False;steps=0
                while isinstance(inner,tuple) and len(inner)==2 and inner[0] in {'not','reverse'}:
                    reverse^=inner[0]=='reverse';flip^=inner[0]=='not';inner=inner[1];steps+=1
                    if steps>16:raise Unsupported('bijective transport depth budget')
                transformed=(transported_kind(e[0],reverse,flip),inner)
                r=self.scalar(transformed)
                self.transport_trace.append({'source':e,'transported_count':transformed,'kind':'bijective-action-on-view'})
            else:
                if e not in self.view_counts:
                    self.view_counts[e]='@n'+str(len(self.counts)+len(self.view_counts))
                    rows,constraints,trace=pullback(self,e[0],view,var(self.view_counts[e]))
                    self.transported_rows.extend(rows);self.view_constraints.extend(constraints)
                    self.transport_trace.append({'source':e,'kind':'partial-row-pullback',**trace})
                r=[(True,var(self.view_counts[e]))]
        elif isinstance(e,tuple) and e[0] in {'add','sub','min','max'} and len(e)==3:
            r=[]
            for ga,a in self.scalar(e[1]):
                for gb,b in self.scalar(e[2]):
                    g=And(ga,gb)
                    if e[0] in {'add','sub'}:r.append((g,(add if e[0]=='add' else sub)(a,b)))
                    else:
                        c=le(a,b);lo,hi=(a,b) if e[0]=='min' else (b,a)
                        r.extend([(And(g,c),lo),(And(g,Not(c)),hi)])
        elif isinstance(e,tuple) and e[0]=='ite' and len(e)==4:
            c=self.boolean(e[1]);r=[(And(c,g),a) for g,a in self.scalar(e[2])]+[(And(Not(c),g),a) for g,a in self.scalar(e[3])]
        else:raise Unsupported('scalar operation '+repr(e))
        r=[(g,a) for g,a in r if g is not False]
        if len(r)>1024:raise Unsupported('scalar piece limit')
        self.scalar_cache[e]=r;return r
    def boolean(self,e):
        if type(e) is bool:return e
        e=tree(e);op=e[0]
        if op in {'and','or'}:return (And if op=='and' else Or)(*(self.boolean(x) for x in e[1:]))
        if op=='not' and len(e)==2:return Not(self.boolean(e[1]))
        if op in {'le','lt','eq'} and len(e)==3:
            cmp={'le':le,'lt':lt,'eq':eq}[op]
            return Or(*(And(ga,gb,cmp(a,b)) for ga,a in self.scalar(e[1]) for gb,b in self.scalar(e[2])))
        raise Unsupported('Boolean operation '+repr(e))
    def bit(self,e,j):
        e=tree(e);key=(e,j)
        if key in self.bit_cache:return self.bit_cache[key]
        if not isinstance(e,tuple):raise Unsupported('word syntax')
        op=e[0];valid=inrange(j)
        if op=='input' and len(e)==2 and e[1] in self.inputs:
            atom=('bit',e[1],j);self.bits.add(atom);r=And(valid,atom)
        elif op=='zero' and len(e)==1:r=False
        elif op=='ones' and len(e)==1:r=valid
        elif op=='not' and len(e)==2:r=And(valid,Not(self.bit(e[1],j)))
        elif op=='reverse' and len(e)==2:r=And(valid,self.bit(e[1],sub(sub(W,const(1)),j)))
        elif op in {'and','or','xor'} and len(e)==3:
            r=And(valid,{'and':And,'or':Or,'xor':Xor}[op](self.bit(e[1],j),self.bit(e[2],j)))
        elif op in {'lowmask','highmask'} and len(e)==2:
            r=Or(*(And(valid,g,lt(j,n) if op=='lowmask' else le(sub(W,n),j)) for g,n in self.scalar(e[1])))
        elif op in {'shl','lshr'} and len(e)==3:
            r=Or(*(And(valid,g,le(const(0),s),lt(s,W),self.bit(e[1],sub(j,s) if op=='shl' else add(j,s))) for g,s in self.scalar(e[2])))
        elif op=='ite' and len(e)==4:
            c=self.boolean(e[1]);r=Or(And(c,self.bit(e[2],j)),And(Not(c),self.bit(e[3],j)))
        else:raise Unsupported('word operation '+repr(e))
        self.bit_cache[key]=r;return r
    def facts(self):
        from interface import observation_plan
        self.added_observations=observation_plan(self.counts,self.interface_level)
        if self.view_counts and self.interface_level==2:
            from transport import regions
            rows=list(self.transported_rows)
            shared={r['word'] for r in rows}
            for (kind,name),nname in self.counts.items():
                if name in shared:
                    rows.extend(dict(r,word=name) for r in regions(sys.modules[__name__],kind,var(nname)))
            positions={(r['word'],lo) for r in rows for lo in r['lower']}
            for name,position in sorted(positions,key=repr):
                self.added_observations.append({'word':name,'index':list(position),'reasons':['transported-domain-start']})
        for observation in self.added_observations:
            self.bit(('input',observation['word']),lin(observation['index']))
        fs=[le(const(1),W)]
        for (kind,name),nname in sorted(self.counts.items()):
            n=var(nname);desired=int(kind.endswith('o'))
            fs.extend([le(const(0),n),le(n,W)])
            for atom in sorted(self.bits,key=repr):
                if atom[1]!=name:continue
                j=atom[2];vr=inrange(j)
                run=le(sub(W,n),j) if kind.startswith('cl') else lt(j,n)
                boundary=sub(sub(W,n),const(1)) if kind.startswith('cl') else n
                fs.append(imply(And(vr,run),atom if desired else Not(atom)))
                fs.append(imply(And(vr,lt(n,W),eq(j,boundary)),Not(atom) if desired else atom))
        fs.extend(self.view_constraints)
        for nname in self.view_counts.values():fs.extend([le(const(0),var(nname)),le(var(nname),W)])
        for row in self.transported_rows:
            for atom in sorted(self.bits,key=repr):
                if atom[1]!=row['word']:continue
                j=atom[2]
                covered=And(row['guard'],inrange(j),*(le(lo,j) for lo in row['lower']),*(lt(j,hi) for hi in row['upper']))
                fs.append(imply(covered,atom if row['bit'] else Not(atom)))
        atoms=sorted(self.bits,key=repr)
        for p,a in enumerate(atoms):
            for b in atoms[p+1:]:
                if a[1]==b[1]:fs.append(imply(eq(a[2],b[2]),iff(a,b)))
        return And(*fs)
    def bad(self,claim):
        op=claim[0]
        if op=='word_eq' and len(claim)==3:
            r=And(inrange(I),Xor(self.bit(claim[1],I),self.bit(claim[2],I)))
        elif op=='bit_is' and len(claim)==4 and type(claim[3]) is int and claim[3] in [0,1]:
            r=Or(*(And(g,Not(self.bit(claim[1],j)) if claim[3] else self.bit(claim[1],j)) for g,j in self.scalar(claim[2])))
        elif op=='scalar' and len(claim)==2:r=Not(self.boolean(claim[1]))
        else:raise Unsupported('claim '+repr(claim))
        assumption=self.boolean(self.source.get('assume',True))
        return And(assumption,self.facts(),r)

class CNF:
    def __init__(self,formula):
        self.atoms={};self.nodes={};self.clauses=[];self.next_id=1
        top=self.encode(formula)
        self.clause([top]);self.formula=formula
    def clause(self,xs):
        if any(x is True for x in xs):return
        vals=set(x for x in xs if x is not False)
        if any(-x in vals for x in vals):return
        self.clauses.append(tuple(sorted(vals)))
    def encode(self,x):
        if type(x) is bool:return x
        if x[0]=='not':
            z=self.encode(x[1]);return not z if type(z) is bool else -z
        if x in self.nodes:return self.nodes[x]
        if x[0]=='and':
            children=[self.encode(c) for c in x[1:]]
            v=self.next_id;self.next_id+=1;self.nodes[x]=v
            for c in children:self.clause([-v,c])
            self.clause([v]+[not c if type(c) is bool else -c for c in children])
            return v
        if x[0] not in {'le','bit'}:raise ValueError('internal atom')
        v=self.next_id;self.next_id+=1;self.nodes[x]=v;self.atoms[v]=x;return v
    def public(self):return {'atoms':[[i,a] for i,a in sorted(self.atoms.items())],'clauses':self.clauses,'variables':self.next_id-1}

def compile_source(source,interface_level=0):
    claims=source.get('claims',[])
    if not isinstance(claims,list) or not claims:raise ValueError('nonempty claims required')
    result=[]
    for claim in claims:
        c=Compiler(source,interface_level);formula=c.bad(claim);cnf=CNF(formula)
        result.append({'cnf':cnf,'counts':sorted(((list(k),v) for k,v in {**c.counts,**c.view_counts}.items()),key=repr),'queried_bits':len(c.bits),'formula_hash':digest(cnf.public()),'added_observations':c.added_observations,'transport_trace':c.transport_trace})
    return result

def propagate(cnf,assignment):
    assignment=dict(assignment)
    while True:
        changes=False;remaining=[]
        for clause in cnf.clauses:
            pending=[];satisfied=False
            for lit in clause:
                if abs(lit) not in assignment:pending.append(lit)
                elif assignment[abs(lit)]==(lit>0):satisfied=True;break
            if satisfied:continue
            if not pending:return assignment,[],True
            if len(pending)==1:
                lit=pending[0];assignment[abs(lit)]=lit>0;changes=True
            remaining.append(tuple(pending))
        if not changes:return assignment,remaining,False

def linear_rows(cnf,assignment):
    rows=[];ids=[]
    for v,truth in sorted(assignment.items()):
        atom=cnf.atoms.get(v)
        if atom is None or atom[0]!='le':continue
        values=dict(atom[1]);c=values.pop('#',0)
        if truth:row={'coeff':values,'bound':-c}
        else:row={'coeff':{k:-x for k,x in values.items()},'bound':c-1}
        rows.append(row);ids.append((v,truth))
    return rows,ids

def verify_farkas(rows,weights):
    if not isinstance(weights,list) or not weights:raise ValueError('empty arithmetic witness')
    coeff={};bound=Fraction(0)
    for entry in weights:
        if not isinstance(entry,list) or len(entry)!=3 or any(type(x) is not int for x in entry):raise ValueError('weight syntax')
        i,num,den=entry
        if i<0 or i>=len(rows) or num<=0 or den<=0:raise ValueError('weight/domain')
        f=Fraction(num,den);bound+=f*rows[i]['bound']
        for name,c in rows[i]['coeff'].items():coeff[name]=coeff.get(name,Fraction(0))+f*c
    if any(coeff.values()) or bound>=0:raise ValueError('not a linear contradiction')

def verify(source,cert,max_nodes=200000):
    if cert.get('schema')!=SCHEMA or cert.get('semantics')!=SEMANTICS:raise ValueError('certificate schema/semantics')
    if cert.get('source_hash')!=digest(source):raise ValueError('source binding')
    level=cert.get('interface_level')
    if type(level) is not int or level not in (0,1,2):raise ValueError('interface level')
    obligations=compile_source(source,level)
    if len(cert.get('proofs',[]))!=len(obligations):raise ValueError('claim coverage')
    stats={'proof_nodes':0,'boolean_leaves':0,'linear_leaves':0,'splits':0,'claims':len(obligations)}
    for compiled,saved in zip(obligations,cert['proofs']):
        cnf=compiled['cnf']
        if saved.get('formula_hash')!=compiled['formula_hash']:raise ValueError('formula binding')
        def visit(node,assignment):
            stats['proof_nodes']+=1
            if stats['proof_nodes']>max_nodes:raise ValueError('replay node budget')
            assignment,remaining,conflict=propagate(cnf,assignment)
            kind=node.get('kind')
            if kind=='boolean':
                if not conflict:raise ValueError('false Boolean closure')
                stats['boolean_leaves']+=1;return
            if kind=='linear':
                rows,_=linear_rows(cnf,assignment);verify_farkas(rows,node['weights'])
                stats['linear_leaves']+=1;return
            if kind=='split':
                v=node['variable']
                if type(v) is not int or v<1 or v>=cnf.next_id or v in assignment:raise ValueError('invalid split')
                stats['splits']+=1
                for truth,key in [(True,'true'),(False,'false')]:
                    branch=dict(assignment);branch[v]=truth;visit(node[key],branch)
                return
            raise ValueError('proof node kind')
        visit(saved['tree'],{})
    return stats
