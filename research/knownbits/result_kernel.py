"""Checked requests for observations of results, rather than entire words.

All new native bridges are valid for w>=2 under total transfer semantics.
Only actual path predicates are available. The whole source checker supplies
the existing authority to the inherited context layer, without new assumptions.
"""
from functools import lru_cache
from qkf_certifier.kernel import at,replace,digest,Z,T,W
from regular_interfaces import tree,order
from symbolic_bridge import path_guards
from semantic_view import LEAVES
import context_kernel as OLD
import action_kernel as ACTION

SCHEMA='qkf-requested-result-observation-v1'
S=('set_sign_bit',Z);ONE=('const',1);TRUE=('true',);FALSE=('false',)
source_authority=OLD.source_authority
MAX_QUERY_NODES=256


@lru_cache(maxsize=30000)
def native(e):
    e=OLD.native(tree(e))
    if e[0] in LEAVES:return e
    t=(e[0],*(native(c) for c in e[1:]))
    if t==S:return S
    if t[0]=='set_sign_bit':return OLD.native(('or',t[1],S))
    if t==('clear_sign_bit',ONE):return ONE
    if t[0]=='clear_sign_bit':return OLD.native(('and',t[1],('not',S)))
    if t[0]=='shl' and t[1]==ONE and t[2]==('sub',W,ONE):return S
    return OLD.native(t)


def neg(p):return OLD.native(('boolxor',p,TRUE))
def land(a,b):return OLD.native(('booland',a,b))
def lor(a,b):return OLD.native(('boolor',a,b))
def lx(a,b):return OLD.native(('boolxor',a,b))
def choice(p,a,b):return lor(land(p,a),land(neg(p),b))
def pred(op,a,b):return native((op,a,b))
def ctx(guards):return OLD.facts([(native(tree(p)),t) for p,t in guards])


class Request:
    def __init__(self,authority=None):self.steps=[];self.memo={};self.authority=authority
    def record(self,word,observation,value,rule,**evidence):
        if len(self.steps)>=MAX_QUERY_NODES:raise ValueError('result observation query budget')
        self.steps.append(dict(word=word,word_hash=digest(word),observation=observation,
                               value=value,rule=rule,**evidence))
        return value
    def sign(self,e,guards):
        e=native(e);g=ctx(guards);key=(e,tuple(g))
        if key in self.memo:return self.memo[key]
        # A scoped fact is accepted only by its actual normalized source guard.
        facts=[(pred('cmp2',e,Z),True,True),(pred('cmp2',e,Z),False,False),
               (pred('cmp6',e,S),True,False),(pred('cmp6',e,S),False,True),
               (pred('cmp6',S,e),True,True),
               (pred('cmp0',e,Z),True,False),(pred('cmp0',e,ONE),True,False),
               (pred('cmp0',e,S),True,True),(pred('cmp0',e,T),True,True)]
        # Native normalization can reverse predicate polarity. Normalize the
        # proposed fact exactly as the actual context was normalized.
        for p,truth,value in facts:
            normalized=ctx([(p,truth)])
            if len(normalized)==1 and normalized[0] in g:
                out=TRUE if value else FALSE
                self.record(e,'sign',out,'actual-path-sign-fact',fact=normalized[0],context_hash=digest(g))
                self.memo[key]=out;return out
        if e in (Z,ONE):out=FALSE;rule='nonnegative-native-constant';evidence={}
        elif e in (T,S):out=TRUE;rule='negative-native-constant';evidence={}
        elif e[0]=='not':out=neg(self.sign(e[1],g));rule='bit-complement';evidence={}
        elif e[0] in {'and','or','xor'}:
            a,b=self.sign(e[1],g),self.sign(e[2],g)
            out={'and':land,'or':lor,'xor':lx}[e[0]](a,b)
            rule='same-coordinate-operation';evidence=dict(protected_values=[0,1])
        elif e[0]=='select':
            p,a,b=e[1:]
            yes=self.sign(a,g+[(p,True)]);no=self.sign(b,g+[(p,False)])
            out=choice(p,yes,no);rule='source-selected-observation';evidence=dict(selector=e)
        elif e[0]=='ashr':
            out=self.sign(e[1],g);rule='arithmetic-shift-sign';evidence=dict(total_saturated_shift=True)
        elif e[0]=='lshr':
            n=e[2]
            zero=ACTION.count_zero(n) if n[0] in ACTION.COUNTS else pred('cmp0',n,Z)
            out=land(native(zero),self.sign(e[1],g));rule='logical-right-shift-sign'
            evidence=dict(cells=[dict(amount=0,sign='input sign'),dict(amount='positive',sign=0)])
        elif e[0]=='shl' and e[2][0] in {'countl_zero','countl_one'}:
            counted=e[2][1] if e[2][0]=='countl_zero' else native(('not',e[2][1]))
            try:
                separation=OLD.disjoint(e[1],counted,g,self.authority)
            except ValueError:
                out=pred('cmp2',e,Z);rule='native-sign-observation';evidence={}
            else:
                out=FALSE;rule='aligned-leading-bit-excluded'
                evidence=dict(counted_word=counted,disjointness=separation,
                    cells=[dict(counted_word='zero',amount='w',sign=0),
                           dict(counted_word='nonzero',selected_position='highest set bit of counted word',payload_bit=0,sign=0)])
        elif e[0]=='sdiv':
            a,b=e[1:];sa,sb=self.sign(a,g),self.sign(b,g)
            overflow=FALSE if sa==FALSE or sb==FALSE else land(pred('cmp0',a,S),pred('cmp0',b,T))
            if sb==TRUE:
                normal=land(neg(sa),pred('cmp9',a,native(('sub',Z,b))))
                out=lor(normal,overflow);variant='negative-divisor'
            else:
                aa=native(('select',sa,('sub',Z,a),a))
                ab=native(('select',sb,('sub',Z,b),b))
                normal=land(lx(sa,sb),pred('cmp9',aa,ab))
                nonzero=lor(normal,overflow)
                out=choice(pred('cmp0',b,Z),neg(sa),nonzero);variant='total-general-divisor'
            rule='signed-quotient-observation-row'
            evidence=dict(variant=variant,dividend_sign=sa,divisor_sign=sb,
                protected_values=[0,1],cells=[
                    dict(condition='divisor zero; dividend nonnegative',sign=1),
                    dict(condition='divisor zero; dividend negative',sign=0),
                    dict(condition='MIN divided by minus one',sign=1),
                    dict(condition='other nonzero divisor; equal signs',sign=0),
                    dict(condition='opposite signs; magnitude dividend below magnitude divisor',sign=0),
                    dict(condition='opposite signs; magnitude dividend at least magnitude divisor',sign=1)],
                magnitude='unsigned interpretation of modular negation for negative words, including MIN')
        else:
            out=pred('cmp2',e,Z);rule='native-sign-observation';evidence={}
        self.record(e,'sign',out,rule,**evidence);self.memo[key]=out;return out
    def high_or_zero(self,e,guards,depth=0):
        if depth>32:raise ValueError('carrier derivation depth')
        e=native(e);g=ctx(guards)
        if e==Z:rule='zero';evidence={}
        else:
            sign=self.sign(e,g)
            condition=lor(pred('cmp0',e,Z),pred('cmp2',e,Z))
            if sign==TRUE:rule='sign-is-one';evidence=dict(sign=sign)
            elif (condition,True) in g:rule='actual-path-carrier';evidence=dict(fact=(condition,True),context_hash=digest(g))
            elif e[0]=='set_high_bits' and e[1]==Z:
                rule='high-prefix-mask';evidence=dict(amount=e[2],semantics='clamp unsigned count to [0,w]; empty or includes top bit')
            elif e[0]=='not' and e[1][0]=='set_low_bits' and e[1][1]==Z:
                rule='complement-low-prefix-mask';evidence=dict(amount=e[1][2],semantics='full low mask gives zero; every shorter low mask omits the top bit')
            elif e[0]=='clear_low_bits' and e[1]==T:
                rule='clear-low-bits-of-ones';evidence=dict(amount=e[2],semantics='empty or high suffix of ones')
            elif e[0]=='shl' and e[1]==T:
                rule='shift-ones-left';evidence=dict(amount=e[2],semantics='saturated shift is zero; unsaturated shift retains top bit')
            elif e[0] in {'and','or'}:
                self.high_or_zero(e[1],g,depth+1);self.high_or_zero(e[2],g,depth+1)
                rule='closed-coordinate-operation';evidence=dict(operation=e[0],
                    cells=[dict(left=a,right=b,top=(a&b if e[0]=='and' else a|b),
                                whole_zero=(not(a&b) if e[0]=='and' else not(a|b)))
                           for a in (0,1) for b in (0,1)])
            elif e[0]=='select':
                self.high_or_zero(e[2],g+[(e[1],True)],depth+1)
                self.high_or_zero(e[3],g+[(e[1],False)],depth+1)
                rule='selected-carrier';evidence=dict(selector=e)
            else:raise ValueError('word not proved zero or unsigned high')
        return self.record(e,'zero-or-high',['zero','unsigned-at-least-2^(w-1)'],rule,**evidence)


def reduce_action_cell(e):
    e=native(e)
    if e[0] in LEAVES:return e,[]
    terms=[];steps=[]
    for c in e[1:]:
        t,p=reduce_action_cell(c);terms.append(t);steps+=p
    e=native((e[0],*terms))
    if e[0] in ACTION.SHIFTS | ACTION.MASKS:
        try:
            value,tail=ACTION.width_tail(e[2],2)
            if value[0]==value[1]==0 and 0<=value[2]<=8:
                label=('constant',value[2]);bound=None
            else:
                bound=ACTION.ge_zero(ACTION.minus(value,(0,1,0)),2);label=('saturated',)
        except ValueError:pass
        else:
            after=native(ACTION.action_expression(e[0],e[1],label))
            steps.append(dict(source=e,after=after,amount_value=value,tail_derivation=tail,
                              action=label,saturation_bound=bound,minimum_width=2))
            return after,steps
    return OLD.cell_view(e),steps


def request(e,observation,guards,authority=None,parameter=None):
    original=tree(e);v=native(original);r=Request(authority)
    if observation=='sign':value=r.sign(v,guards)
    elif observation=='zero-or-high':value=r.high_or_zero(v,guards)
    elif observation=='word':
        value=OLD.cell_view(v);r.record(v,'word',value,'universal-native-cell-identities')
    elif observation=='action-on-word':
        if v[0] not in ACTION.SHIFTS | ACTION.MASKS or not isinstance(parameter,dict) or set(parameter)!={'selector'}:
            raise ValueError('source action request parameters')
        selector=native(tree(parameter['selector']))
        if selector[0]!='select' or selector not in order(v[2]):raise ValueError('selector not in the source action amount')
        cells=[]
        for truth in (False,True):
            word=OLD.substitute(v,selector,selector[2 if truth else 3]);out,proof=reduce_action_cell(word)
            cells.append(dict(truth=truth,instantiated=word,after=out,action_derivation=proof))
        value=native(('select',selector[1],cells[1]['after'],cells[0]['after']))
        r.record(v,'action-on-word',value,'source-selected-action-row',selector=selector,cells=cells)
    else:raise ValueError('unsupported requested observation')
    return value,dict(kind='requested-result-interface',minimum_width=2,source_hash=digest(original),
        view=v,observation=observation,guards_hash=digest(guards),authority_hash=None if authority is None else digest(authority),value=value,steps=r.steps)


def sign_consumer(e):
    e=native(e);op=e[0]
    if op=='and':
        items=[]
        def flatten(t):
            if t[0]=='and':flatten(t[1]);flatten(t[2])
            else:items.append(t)
        flatten(e)
        if S in items:
            items.remove(S)
            if not items:return None
            word=items[0]
            for t in items[1:]:word=('and',word,t)
            return dict(word=native(word),output='mask',inverted=False)
    if op=='cmp2' and e[2]==Z:return dict(word=e[1],output='predicate',inverted=False)
    if op=='cmp6' and e[2]==S:return dict(word=e[1],output='predicate',inverted=True)
    if op=='cmp0':
        other=e[2] if e[1]==Z else e[1] if e[2]==Z else None
        if other is not None:
            d=sign_consumer(other)
            if d is not None and d['output']=='mask':return dict(d,output='predicate',inverted=True)
    if op=='boolxor' and TRUE in e[1:]:
        d=sign_consumer(e[2] if e[1]==TRUE else e[1])
        if d is not None and d['output']=='predicate':return dict(d,inverted=not d['inverted'])
    if op in {'lshr','ashr'} and e[2]==('sub',W,ONE):
        return dict(word=e[1],output='unit' if op=='lshr' else 'fill',inverted=False)
    return None


def derive(e,guards,kind,parameter=None,authority=None):
    original=tree(e);v=native(original)
    if kind!='action-on-word' and parameter is not None:raise ValueError('unexpected observation parameter')
    if kind=='sign':
        d=sign_consumer(v)
        if d is None:raise ValueError('not a sign-observing consumer')
        p,interface=request(d['word'],'sign',guards,authority)
        if d['inverted']:p=neg(p)
        if d['output']=='predicate':after=p
        else:after=native(('select',p,{'mask':S,'unit':ONE,'fill':T}[d['output']],Z))
        evidence=dict(consumer=d,interface=interface,protected_values=[0,1])
    elif kind=='division-action':
        if v[0] not in {'urem','udiv'}:raise ValueError('not an unsigned division consumer')
        a,b=v[1:];_,interface=request(b,'zero-or-high',guards,authority)
        if v[0]=='urem':after=native(('select',pred('cmp9',a,b),('sub',a,b),a))
        else:after=native(('select',pred('cmp0',b,Z),T,('select',pred('cmp9',a,b),ONE,Z)))
        evidence=dict(interface=interface,cells=[
            dict(divisor='zero',quotient='ones',remainder='dividend'),
            dict(divisor='unsigned high; dividend below divisor',quotient=0,remainder='dividend'),
            dict(divisor='unsigned high; dividend at least divisor',quotient=1,remainder='dividend minus divisor')],
            bound='0<=A<2^w and 2^(w-1)<=D<2^w imply 0<=floor(A/D)<=1')
    elif kind in {'action-on-word','word'}:
        after,interface=request(v,kind,guards,authority,parameter)
        evidence=dict(interface=interface)
    else:raise ValueError('result observation kind')
    return after,dict(kind='requested-'+kind,minimum_width=2,source_hash=digest(original),
                      view=v,guards_hash=digest(guards),after_hash=digest(after),**evidence)


def proof_steps(p):
    if not p['kind'].startswith('requested-'):return OLD.proof_steps(p)
    return len(p['interface']['steps'])+len(p.get('cells',[]))+1


def replay(initial,trace,expected,authority=None):
    root=tree(initial);steps=0
    if not isinstance(trace,list) or len(trace)>1000:raise ValueError('result observation trace budget')
    for t in trace:
        if t['schema']!=SCHEMA:
            nxt=replace(root,t['path'],tree(t['after']));root,n=OLD.replay(root,[t],nxt,authority);steps+=n;continue
        if t['minimum_width']!=2 or digest(root)!=t['before_hash']:raise ValueError('result request source binding')
        g=path_guards(root,t['path']);after,p=derive(at(root,t['path']),g,t['kind'],t.get('parameter'),authority)
        if digest(g)!=digest(t['guards']) or digest(p)!=digest(t['proof']) or after!=tree(t['after']):raise ValueError('result request derivation mismatch')
        root=replace(root,t['path'],after);steps+=proof_steps(p)
        if digest(root)!=t['after_hash']:raise ValueError('result request output binding')
    if root!=tree(expected):raise ValueError('result request final mismatch')
    return root,steps
