"""Independent fixed-width SSA transcription of the complete selected Java bodies.

Scalars have Java long semantics (64 bits), comparisons are signed, and shift
amounts use Java's low six bits. Source loops are expanded at the declared
width; create keeps all three iterations, early returns and explicit failures.
This infrastructure is separate from the frozen QKF all-width word language.
"""
import dataclasses,json,sys
sys.setrecursionlimit(20000)
M64=(1<<64)-1


def jlong(x):
    x&=M64
    return x-(1<<64) if x>>63 else x


def operation(op,x):
    if op=='add':return jlong(x[0]+x[1])
    if op=='sub':return jlong(x[0]-x[1])
    if op=='and':return x[0]&x[1]
    if op=='or':return x[0]|x[1]
    if op=='xor':return x[0]^x[1]
    if op=='not':return ~x[0]
    if op=='shl':return jlong(x[0]<<(x[1]&63))
    if op=='ashr':return x[0]>>(x[1]&63)
    if op=='lshr':return jlong((x[0]&M64)>>(x[1]&63))
    if op=='eq':return x[0]==x[1]
    if op=='lt':return x[0]<x[1]
    if op=='le':return x[0]<=x[1]
    if op=='band':return x[0] and x[1]
    if op=='bor':return x[0] or x[1]
    if op=='bnot':return not x[0]
    if op=='clz':return 64-(x[0]&M64).bit_length()
    if op=='ctz':return 64 if not x[0] else ((x[0]&M64)&-(x[0]&M64)).bit_length()-1
    if op=='select':return x[1] if x[0] else x[2]
    raise ValueError(op)


class Ref:
    def __init__(self,ir,index,kind):self.ir=ir;self.index=index;self.kind=kind
    def __bool__(self):raise TypeError('symbolic truth used as Python control flow')
    def __add__(self,b):return self.ir.op('add',self,b)
    def __radd__(self,b):return self.ir.op('add',b,self)
    def __sub__(self,b):return self.ir.op('sub',self,b)
    def __rsub__(self,b):return self.ir.op('sub',b,self)
    def __neg__(self):return 0-self
    def __and__(self,b):return self.ir.op('band' if self.kind=='bool' else 'and',self,b)
    def __rand__(self,b):return self.__and__(b)
    def __or__(self,b):return self.ir.op('bor' if self.kind=='bool' else 'or',self,b)
    def __ror__(self,b):return self.__or__(b)
    def __xor__(self,b):return self.ir.op('xor',self,b)
    def __invert__(self):return self.ir.op('bnot' if self.kind=='bool' else 'not',self)
    def __lshift__(self,b):return self.ir.op('shl',self,b)
    def __rshift__(self,b):return self.ir.op('ashr',self,b)
    def __lt__(self,b):return self.ir.op('lt',self,b)
    def __le__(self,b):return self.ir.op('le',self,b)
    def __gt__(self,b):return self.ir.op('lt',b,self)
    def __ge__(self,b):return self.ir.op('le',b,self)
    def eq(self,b):return self.ir.op('eq',self,b)
    def ne(self,b):return ~self.eq(b)


class IR:
    def __init__(self,width):self.width=width;self.nodes=[];self.cache={}
    def intern(self,op,args,kind):
        key=(op,tuple(args),kind)
        if key not in self.cache:
            self.cache[key]=Ref(self,len(self.nodes),kind)
            self.nodes.append(dict(op=op,args=list(args),kind=kind))
        return self.cache[key]
    def constant(self,v):return self.intern('const',[v if type(v)is bool else jlong(v)],'bool' if type(v)is bool else 'long')
    def ref(self,v):return v if isinstance(v,Ref) else self.constant(v)
    def var(self,i):return self.intern('var',[i],'long')
    def op(self,op,*args):
        args=[self.ref(v) for v in args]
        if all(self.nodes[v.index]['op']=='const' for v in args):
            return self.constant(operation(op,[self.nodes[v.index]['args'][0] for v in args]))
        if op=='select' and self.nodes[args[0].index]['op']=='const':return args[1 if self.nodes[args[0].index]['args'][0] else 2]
        kind='bool' if op in {'eq','lt','le','band','bor','bnot'} else args[1].kind if op=='select' else 'long'
        return self.intern(op,[v.index for v in args],kind)
    def select(self,p,a,b):return self.op('select',p,a,b)
    def clz(self,x):return self.op('clz',x)
    def ctz(self,x):return self.op('ctz',x)
    def ushr(self,x,n):return self.op('lshr',x,n)
    def minimum(self,a,b):return self.select(self.ref(a)<b,a,b)
    def maximum(self,a,b):return self.select(self.ref(a)>b,a,b)
    def mask(self,n):
        if isinstance(n,int):return self.constant(-1 if n==64 else (1<<n)-1)
        return self.select(n.eq(64),-1,(self.constant(1)<<n)-1)
    def sign_extend(self,x):return (self.ref(x)<<(64-self.width))>>(64-self.width) if self.width<64 else self.ref(x)
    def evaluate(self,outputs,values):
        cache={}
        def at(i):
            if i in cache:return cache[i]
            n=self.nodes[i];op=n['op'];args=n['args']
            if op=='const':v=args[0]
            elif op=='var':v=jlong(values[args[0]])
            elif op=='select':v=at(args[1] if at(args[0]) else args[2])
            elif op=='band':v=at(args[0]) and at(args[1])
            elif op=='bor':v=at(args[0]) or at(args[1])
            else:v=operation(op,[at(a) for a in args])
            cache[i]=v;return v
        return tuple(at(v.index if isinstance(v,Ref) else v) for v in outputs)


@dataclasses.dataclass
class Stamp:
    lo:Ref;hi:Ref;must:Ref;may:Ref;zero:Ref;failed:Ref
    def values(self):return [self.lo,self.hi,self.must,self.may,self.zero,self.failed]


class Graal:
    def __init__(self,width):
        self.ir=IR(width);self.bits=width;self.mask=self.ir.mask(width)
        self.low=self.ir.constant(-(1<<(width-1)));self.high=self.ir.constant((1<<(width-1))-1)
        self.false=self.ir.constant(False);self.true=self.ir.constant(True)
    def choose(self,p,a,b):return Stamp(*(self.ir.select(p,x,y) for x,y in zip(a.values(),b.values())))
    def raw(self,lo,hi,must,may,zero=True,failed=False):
        r=self.ir;lo,hi,must,may,zero,failed=map(r.ref,[lo,hi,must,may,zero,failed])
        canzero=(zero | (lo.eq(0)&hi.eq(0))) & (lo<=0) & (hi>=0) & must.eq(0)
        return Stamp(lo,hi,must,may,canzero,failed)
    def empty(self):return self.raw(self.high,self.low,self.mask,0,False)
    def is_empty(self,s):return s.lo>s.hi
    def bad(self,lo,hi,must,may):return (lo>hi) | (must & ~may).ne(0) | (may.eq(0)&((lo>0)|(hi<0)))
    def sign(self,x):return (self.ir.ushr(x,self.bits-1)&1).eq(1)
    def min_masks(self,must,may):return self.ir.select(self.sign(may),must | (self.ir.constant(-1)<<(self.bits-1)),must)
    def max_masks(self,must,may):return self.ir.select(self.sign(must),self.ir.sign_extend(may),may & self.ir.ushr(self.mask,1))
    def for_mask(self,must,may):
        s=self.raw(self.min_masks(must,may),self.max_masks(must,may),must,may)
        return self.choose((must & ~may).ne(0),self.empty(),s)
    def constant(self,x):return self.raw(x,x,x&self.mask,x&self.mask,x.eq(0))
    def range(self,lo,hi):
        r=self.ir;bits=r.ushr(-1,r.clz(lo^hi));s=self.raw(lo,hi,self.mask&(lo&~bits),self.mask&(lo|bits))
        return self.choose(lo>hi,self.empty(),self.choose(lo.eq(hi),self.constant(lo),s))
    def upper(self,bound,must,may,zero):
        r=self.ir;v=r.sign_extend(must)
        v=r.select((bound<0)|(v>bound),self.min_masks(must,may),v)
        optional=may & ~must & r.mask(self.bits-1)
        for p in range(self.bits-1,-1,-1):
            bit=r.constant(1)<<p
            v=r.select((bit&optional).ne(0)&((v|bit)<=bound),v|bit,v)
        negative=r.select(~self.sign(may),self.low,self.max_masks(must|(r.constant(1)<<(self.bits-1)),may))
        v=r.select(v.eq(0)&~zero,negative,v)
        return r.select(v>bound,self.low,v)
    def lower(self,bound,must,may,zero):
        r=self.ir;v=self.min_masks(must,may);optional=may & ~must & r.mask(self.bits-1)
        below=v<bound;walk=v
        for p in range(self.bits-1,-1,-1):
            bit=r.constant(1)<<p
            walk=r.select((bit&optional).ne(0)&((walk+bit)<=bound),walk+bit,walk)
        fail=below & optional.ne(0) & (walk>bound)
        smaller=walk<bound;inc=self.false;raised=walk
        for p in range(self.bits-1):
            bit=r.constant(1)<<p
            fixed=r.select((bit&must).ne(0)&(raised&bit).eq(0),raised|bit,raised)
            fixed=r.select((bit&may).eq(0)&(fixed&bit).ne(0),fixed+bit,fixed)
            raised=r.select(inc,fixed,r.select((bit&optional).ne(0),raised+bit,raised))
            inc=inc | (bit&optional).ne(0)
        walk=r.select(smaller,raised,walk)
        v=r.select(below,r.select(optional.eq(0),0,walk),v)
        positive=r.select(must>0,must,r.select(must.eq(0),r.constant(1)<<r.ctz(may),self.high))
        v=r.select(v.eq(0)&~zero,positive,v)
        return r.select(v<bound,self.high,v),fail
    def create(self,lo,hi,must,may,zero=True):
        r=self.ir;lo,hi,must,may,zero=map(r.ref,[lo,hi,must,may,zero])
        original_bad=self.bad(lo,hi,must,may)
        trivial=must.eq(0)&may.eq(self.mask)&zero
        result=self.empty();active=self.true;failed=self.false
        oldlo,oldhi,oldmust,oldmay=lo,hi,must,may
        for _ in range(3):
            nl=r.maximum(lo,self.min_masks(must,may));nh=r.minimum(hi,self.max_masks(must,may))
            equal=nl.eq(nh);same=r.ushr(-1,r.clz(nl^nh))
            boundedmust=r.select(equal,nl,nl&~same);boundedmay=r.select(equal,nl,nl|same)
            nm=self.mask & (must|boundedmust);ny=self.mask & may & boundedmay
            nh=r.minimum(nh,self.max_masks(nm,ny));nl=r.maximum(nl,self.min_masks(nm,ny))
            nh=self.upper(nh,nm,ny,zero);nl,helper_failed=self.lower(nl,nm,ny,zero)
            empty=self.bad(nl,nh,nm,ny);stable=lo.eq(nl)&hi.eq(nh)&must.eq(nm)&may.eq(ny)
            current=self.raw(nl,nh,nm,ny,zero)
            result=self.choose(active&(empty|stable),self.choose(empty,self.empty(),current),result)
            failed=failed | (active & helper_failed) | (active & ~empty & ~stable & ((nl<lo)|(nh>hi)))
            active=active & ~empty & ~stable
            lo,hi,must,may=nl,nh,nm,ny
        result.failed=result.failed | failed | active
        result=self.choose(trivial,self.range(oldlo,oldhi),result)
        return self.choose(original_bad,self.empty(),result)
    def unrestricted(self,s):return s.lo.eq(self.low)&s.hi.eq(self.high)&s.must.eq(0)&s.may.eq(self.mask)&s.zero
    def add(self,a,b):
        r=self.ir
        variable=(a.must^a.may)|(b.must^b.may)
        carrylo=(a.must+b.must)^a.must^b.must;carryhi=(a.may+b.may)^a.may^b.may
        varying=variable|(carrylo^carryhi)
        must=((a.must+b.must)&~varying)&self.mask;may=((a.must+b.must)|varying)&self.mask
        def pos(x,y):return (~x & ~y & (x+y))<0 if self.bits==64 else (x+y)>self.high
        def neg(x,y):return (x & y & ~(x+y))<0 if self.bits==64 else (x+y)<self.low
        lp,up,ln,un=pos(a.lo,b.lo),pos(a.hi,b.hi),neg(a.lo,b.lo),neg(a.hi,b.hi)
        full=(ln&~un)|(~lp&up)
        lo=r.select(full,self.low,r.sign_extend((a.lo+b.lo)&self.mask))
        hi=r.select(full,self.high,r.sign_extend((a.hi+b.hi)&self.mask))
        limit=self.range(lo,hi);may=may&limit.may;hi=r.sign_extend(hi&may);must=must|limit.must;lo=lo|must
        out=self.create(lo,hi,must,may)
        out=self.choose(self.unrestricted(b),b,out);out=self.choose(self.unrestricted(a),a,out)
        out=self.choose(a.lo.eq(a.hi)&b.lo.eq(b.hi),self.constant(r.sign_extend(a.lo+b.lo)),out)
        out=self.choose(self.is_empty(b),b,out);out=self.choose(self.is_empty(a),a,out)
        out.failed=out.failed|a.failed|b.failed;return out
    def neg(self,a):
        r=self.ir;may=~r.mask(r.ctz(a.may)) & self.mask
        out=self.choose(a.lo.ne(self.low),self.create(-a.hi,-a.lo,r.constant(0),may),self.for_mask(r.constant(0),may))
        out=self.choose(a.lo.eq(a.hi),self.constant(r.sign_extend(-a.lo)),out)
        out=self.choose(self.is_empty(a),a,out);out.failed=out.failed|a.failed;return out
    def bitnot(self,a):
        out=self.create(~a.hi,~a.lo,(~a.may)&self.mask,(~a.must)&self.mask)
        out=self.choose(self.is_empty(a),a,out);out.failed=out.failed|a.failed;return out
    def bitand(self,a,b):
        r=self.ir;must=a.must&b.must;may=a.may&b.may
        upper=self.max_masks(must,may)
        upper=r.select(a.lo>=0,r.minimum(upper,a.hi),upper);upper=r.select(b.lo>=0,r.minimum(upper,b.hi),upper)
        positive=self.create(r.constant(0),upper,must,may)
        upperneg=r.minimum(self.max_masks(must,may),r.minimum(a.hi,b.hi))
        negative=self.create(self.min_masks(must,may),upperneg,must,may)
        out=self.choose(~self.sign(may),positive,self.choose(self.sign(must),negative,self.for_mask(must,may)))
        out=self.choose(self.is_empty(b),b,out);out=self.choose(self.is_empty(a),a,out)
        out.failed=out.failed|a.failed|b.failed;return out
    def bitor(self,a,b):
        out=self.for_mask(a.must|b.must,a.may|b.may)
        out=self.choose(self.is_empty(b),b,out);out=self.choose(self.is_empty(a),a,out)
        out.failed=out.failed|a.failed|b.failed;return out
    def bitxor(self,a,b):
        variable=(a.must^a.may)|(b.must^b.may)
        out=self.for_mask((a.must^b.must)&~variable,(a.must^b.must)|variable)
        out=self.choose(a.lo.eq(-1)&a.hi.eq(-1),self.bitnot(b),out)
        out=self.choose(b.lo.eq(-1)&b.hi.eq(-1),self.bitnot(a),out)
        out=self.choose(self.is_empty(b),b,out);out=self.choose(self.is_empty(a),a,out)
        out.failed=out.failed|a.failed|b.failed;return out
    def build(self,op):
        v=[self.ir.var(i) for i in range(4)]
        a=self.for_mask(v[1],~v[0]&self.mask);b=self.for_mask(v[3],~v[2]&self.mask)
        if op=='sub':out=self.add(a,self.neg(b))
        else:out={'and':self.bitand,'or':self.bitor,'xor':self.bitxor,'add':self.add}[op](a,b)
        return out


def build(op,width):
    model=Graal(width);out=model.build(op)
    return model.ir,out.values()


def dump(op,width):
    ir,out=build(op,width)
    return dict(schema='graal-java-long-ssa-v1',operation=op,width=width,scalar_width=64,
                nodes=ir.nodes,outputs=[x.index for x in out],source_loops='all 3 refinement rounds and all width-dependent bit positions')


if __name__=='__main__':
    for op in ['and','or','xor','add','sub']:
        ir,out=build(op,4);print(op,len(ir.nodes),ir.evaluate(out,[8,1,4,2]))
