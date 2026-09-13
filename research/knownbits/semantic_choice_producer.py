"""Same consumers and cost policy, with interchangeable observation engines."""
import collections,json
from qkf_certifier.kernel import at,replace,digest,children
from symbolic_bridge import path_guards
from regular_interfaces import order
from prefix_masks import lower,allowed_node
from semantic_view import source_view
import observation_kernel as OLD
import observation_producer as PREVIOUS
import row_observation_producer as ROW
import semantic_choice_kernel as K


def cover(e,guards,mode):
    if mode=='rows':return dict(engine='rows',certificate=ROW.produce(e,guards))
    v,g=source_view(e,guards);values,proof=OLD.support(v,g)
    return dict(engine='views',source_hash=digest(e),guards_hash=digest(guards),view_hash=digest(v),values=values,proof=proof)


def cost(after,proof):
    nodes=order(lower(after))
    return [sum(not allowed_node(t) for t in nodes),sum(t[0].startswith('cmp') for t in nodes),
      sum(t[0] in {'add','sub','shl','lshr','ashr'} or t[0].startswith('run_') for t in nodes),len(nodes),K.proof_steps(proof)]


def produce(initial,mode):
    if mode=='previous':return PREVIOUS.produce(initial,'adaptive')
    if mode not in {'views','rows'}:raise ValueError('inference mode')
    root=initial;trace=[];trials=[];queries=[];cache={};failures=collections.Counter();attempts=0
    def query(e,g):
        key=(e,tuple(g))
        if key in cache:
            ok,value=cache[key]
            if ok:return value
            raise ValueError(value)
        try:
            result=cover(e,g,mode);cache[key]=(True,result)
            vals=result['certificate']['values'] if mode=='rows' else result['values']
            queries.append(dict(source_hash=digest(e),guards_hash=digest(g),status='covered',values=vals,
                stats=result['certificate']['stats'] if mode=='rows' else None));return result
        except ValueError as ex:
            reason=str(ex);cache[key]=(False,reason);queries.append(dict(source_hash=digest(e),guards_hash=digest(g),status='unresolved',reason=reason));raise
    def attempt(path):
        nonlocal root,attempts
        e=at(root,path);g=path_guards(root,path);choices=[]
        for kind,p in PREVIOUS.choices(e,'adaptive'):
            if kind in {'finite-row','joint-binary'}:continue
            choices.append((kind,p))
        if e[0]=='mul':
            cs={}
            for side in (1,2):
                try:cs[side]=query(e[side],g)
                except ValueError:pass
            if len(cs)==2:choices.append(('semantic-joint-binary',dict(left=cs[1],right=cs[2])))
            for side,c in cs.items():
                for obs in ['zero','parity','exact']:choices.append(('semantic-finite-row',dict(side=side,observation=obs,cover=c)))
        accepted=[];rejected=[]
        for kind,p in choices:
            attempts+=1
            try:after,proof,guards=K.derive(root,path,kind,p)
            except ValueError as ex:
                failures[str(ex)]+=1
                if str(ex).startswith('{'):rejected.append(json.loads(str(ex)))
                continue
            if after==e:continue
            accepted.append(dict(kind=kind,parameter=p,after=after,proof=proof,guards=guards,cost=cost(after,proof)))
        if not accepted:
            if rejected:trials.append(dict(path=path,before=digest(e),accepted=[],rejected=rejected))
            return False
        selected=min(accepted,key=lambda c:c['cost']);after=replace(root,path,selected['after'])
        trials.append(dict(path=path,before=digest(e),accepted=[dict(kind=c['kind'],cost=c['cost']) for c in accepted],rejected=rejected,
          selected=dict(kind=selected['kind'],cost=selected['cost'])))
        trace.append(dict(schema=K.SCHEMA,minimum_width=2,path=path,kind=selected['kind'],parameter=selected['parameter'],after=selected['after'],proof=selected['proof'],guards=selected['guards'],before_hash=digest(root),after_hash=digest(after)))
        root=after
        if len(trace)>1000:raise ValueError('observation rewrite budget')
        return True
    def visit(path):
        while attempt(path):pass
        for i in children(at(root,path)):visit(path+[i])
        if attempt(path):visit(path)
    visit([])
    return root,trace,dict(trials=trials,attempts=attempts,accepted=len(trace),support_queries=queries,
        failures=dict(failures),selected_proof_steps=sum(K.proof_steps(t['proof']) for t in trace))
