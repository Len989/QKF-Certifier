"""Checked exhaustive source-derived case splits and conditional invariants.

The existing bit-transition interpreter is unchanged. A leaf restricts INITIAL
comparison guesses to its actual Boolean guard, and still validates all guessed
comparisons at the terminal bit. The decision tree covers both outcomes of each
source-derived predicate. Propositional reasoning is finite truth-table logic,
not an SMT call. See PROOFS.md for the two composition lemmas.
"""
from functools import lru_cache
from qkf_certifier.kernel import Z,T,W,TRUE,FALSE,children,at,digest
from regular_interfaces import COMPS,LEAVES,tree,check_invariant
from prove_umin import LengthMachine
from prefix_masks import lower,supported

EXTENSION='qkf-source-case-composition-v2'
MAX_ATOMS=16

def atoms(e):
    if e[0] in COMPS:return {e}
    if e in (TRUE,FALSE):return set()
    if e[0] in {'booland','boolor','boolxor'}:return atoms(e[1])|atoms(e[2])
    raise ValueError('not a Boolean guard')

def bool_value(e,values):
    if e==TRUE:return True
    if e==FALSE:return False
    if e[0] in COMPS:return bool(values[e])
    a,b=bool_value(e[1],values),bool_value(e[2],values)
    if e[0]=='booland':return a and b
    if e[0]=='boolor':return a or b
    if e[0]=='boolxor':return a!=b
    raise ValueError('Boolean operation')

def truth_bits(e,values,all_bits):
    if e==TRUE:return all_bits
    if e==FALSE:return 0
    if e[0] in COMPS:return values[e]
    a,b=truth_bits(e[1],values,all_bits),truth_bits(e[2],values,all_bits)
    if e[0]=='booland':return a&b
    if e[0]=='boolor':return a|b
    if e[0]=='boolxor':return a^b
    raise ValueError('Boolean operation')

@lru_cache(maxsize=30000)
def consequence(path,query):
    """True/False only if every propositional model of the path forces it."""
    aa=atoms(query)
    for p,_ in path:aa|=atoms(p)
    if len(aa)>MAX_ATOMS:return None
    aa=sorted(aa,key=repr);k=len(aa);all_bits=(1<<(1<<k))-1;values={}
    for i,a in enumerate(aa):
        block=1<<i;values[a]=(((1<<block)-1)<<block)*(all_bits//((1<<(2*block))-1))
    models=all_bits
    for p,v in path:
        q=truth_bits(p,values,all_bits);models&=q if v else all_bits^q
    if models==0:return 'empty'
    q=truth_bits(query,values,all_bits)
    if models&~q==0:return True
    if models&q==0:return False
    return None

def literal(e):
    return 0 if e==Z else -1 if e==T else e[1] if e[0]=='const' else None
def const(n):return Z if n==0 else T if n==-1 else ('const',n)

def local(e):
    """Small total semantic simplifier. No use of branch assumptions here."""
    op=e[0];a=e[1] if len(e)>1 else None;b=e[2] if len(e)>2 else None
    if op=='select':
        if a in (TRUE,FALSE):return e[2] if a==TRUE else e[3]
        if e[2]==e[3]:return e[2]
    if op in {'booland','boolor','boolxor'}:
        if a in (TRUE,FALSE) and b in (TRUE,FALSE):return TRUE if bool_value(e,{}) else FALSE
        if a==b:return FALSE if op=='boolxor' else a
        if op=='booland':
            if FALSE in (a,b):return FALSE
            if a==TRUE:return b
            if b==TRUE:return a
        if op=='boolor':
            if TRUE in (a,b):return TRUE
            if a==FALSE:return b
            if b==FALSE:return a
        if op=='boolxor':
            if a==FALSE:return b
            if b==FALSE:return a
            if a==TRUE and b[0]=='boolxor' and b[2]==TRUE:return b[1]
            if b==TRUE and a[0]=='boolxor' and a[2]==TRUE:return a[1]
    if op in COMPS and a==b:return TRUE if int(op[3:]) in (0,3,5,7,9) else FALSE
    if op in {'and','or','xor','add','sub'}:
        x,y=literal(a),literal(b)
        if x is not None and y is not None:
            return const({'and':lambda:x&y,'or':lambda:x|y,'xor':lambda:x^y,'add':lambda:x+y,'sub':lambda:x-y}[op]())
        if op=='and':
            if Z in (a,b):return Z
            if a==T:return b
            if b==T:return a
            if a==b:return a
        if op=='or':
            if T in (a,b):return T
            if a==Z:return b
            if b==Z:return a
            if a==b:return a
        if op in {'xor','add'} and a==Z:return b
        if op in {'xor','add','sub'} and b==Z:return a
        if op in {'xor','sub'} and a==b:return Z
    if op=='not':
        x=literal(a)
        if x is not None:return const(~x)
        if a[0]=='not':return a[1]
    if op.startswith(('countl_','countr_')) and a in (Z,T):
        return W if ((a==T)==op.endswith('one')) else Z
    if op in {'set_low_bits','set_high_bits','clear_low_bits','clear_high_bits'}:
        if b==Z:return a
        if b==W:return T if op.startswith('set') else Z
        if op.startswith('clear') and a==Z:return Z
        if op.startswith('set') and a==T:return T
    if op=='clear_sign_bit' and a==Z:return Z
    return e

@lru_cache(maxsize=4096)
def word_bindings(path):
    available=set()
    for p,_ in path:available|=atoms(p)
    out={}
    for atom in sorted(available,key=repr):
        if atom[0] not in {'cmp0','cmp1'}:continue
        v=consequence(path,atom)
        if not((atom[0]=='cmp0' and v is True) or (atom[0]=='cmp1' and v is False)):continue
        for a,b in [(atom[1],atom[2]),(atom[2],atom[1])]:
            if a[0]=='var' and a[1]<4 and b in (Z,T):out[a]=b
    for v,c in list(out.items()):
        if c==T:out[('var',v[1]^1)]=Z
    return out

def specialize(root,path):
    """Exactly equals root on inputs satisfying the actual path conditions."""
    path=tuple(path);bindings=word_bindings(path)
    @lru_cache(None)
    def visit(e):
        if e in bindings:return bindings[e]
        if e[0] in LEAVES or e==W:return e
        if e[0]=='select':
            known=consequence(path,e[1])
            if known is True or known is False:return visit(e[2] if known else e[3])
            c=visit(e[1]);known=consequence(path,c)
            if known is True or known is False:return visit(e[2] if known else e[3])
            return local(('select',c,visit(e[2]),visit(e[3])))
        new=local((e[0],*(visit(c) for c in e[1:])))
        if new[0] in COMPS or new[0] in {'booland','boolor','boolxor'}:
            known=consequence(path,new)
            if known is True or known is False:return TRUE if known else FALSE
        return new
    return visit(root)

def guard(path):
    result=TRUE
    for p,value in path:result=local(('booland',result,p if value else local(('boolxor',p,TRUE))))
    return result

def first_select(e,path=()):
    if e[0]=='select':return path
    # Selects inside a predicate remain part of its exact word semantics. They
    # are not independently split as though they were visible output branches.
    if e[0] in COMPS:return None
    for i in children(e):
        found=first_select(e[i],path+(i,))
        if found is not None:return found
    return None

class GuardMachine(LengthMachine):
    def __init__(self,candidate,target,path,attempt_budget=None):
        g=guard(path)
        wrapped=('pair',('select',g,candidate[1],Z),('select',g,candidate[2],Z))
        super().__init__(wrapped,target,attempt_budget)
        cg=lower(g)
        # All guards are evaluated against the actual comparison nodes in the
        # compiled source DAG. The producer cannot supply a pruned state list.
        self.unrestricted_initial_count=len(self.initial)
        self.initial=tuple(s for s in self.initial if bool_value(cg,{c:s[1][i] for c,i in self.ci.items()}))

def verify_tree(initial,target,certificate,path=(),depth=0,counts=None):
    if counts is None:counts={'leaves':0,'states':0,'transitions':0,'branches':0}
    if depth>24:raise ValueError('decision depth limit')
    if consequence(path,TRUE)=='empty':
        if certificate!={'kind':'propositionally_empty'}:raise ValueError('empty-path certificate')
        counts['leaves']+=1;return counts
    current=specialize(initial,path);kind=certificate['kind']
    if kind=='split':
        p=tuple(certificate['select_path']);node=at(current,p)
        if node[0]!='select' or digest(node[1])!=certificate['predicate_hash']:raise ValueError('split not bound to source')
        if set(certificate)!={'kind','select_path','predicate_hash','true','false'}:raise ValueError('split fields')
        counts['branches']+=1
        verify_tree(initial,target,certificate['true'],path+((node[1],True),),depth+1,counts)
        verify_tree(initial,target,certificate['false'],path+((node[1],False),),depth+1,counts)
        return counts
    counts['leaves']+=1
    if counts['leaves']>512:raise ValueError('leaf limit')
    if certificate.get('expression_hash')!=digest(current) or certificate.get('guard_hash')!=digest(guard(path)):raise ValueError('leaf binding')
    if kind=='top':
        if current!=('pair',Z,Z):raise ValueError('not top')
        return counts
    if kind!='invariant':raise ValueError('unknown leaf kind')
    indices=certificate['assumption_indices']
    if not isinstance(indices,list) or any(type(i) is not int or not 0<=i<len(path) for i in indices) or indices!=sorted(set(indices)):
        raise ValueError('invalid weakened guard selection')
    weaker=tuple(path[i] for i in indices)
    if certificate['proof_guard_hash']!=digest(guard(weaker)):raise ValueError('weakened guard binding')
    m=GuardMachine(current,target,weaker);states=certificate['invariant']
    counts['states']+=len(states)
    if counts['states']>100000:raise ValueError('aggregate state limit')
    if not m.initial:
        if states:raise ValueError('nonempty proof for empty initials')
        checks=0
    else:checks=check_invariant(m,states)
    counts['transitions']+=checks
    return counts
