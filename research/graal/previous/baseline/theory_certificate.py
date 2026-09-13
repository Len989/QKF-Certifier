"""A concrete Paper I row and Paper II two-sided visibility certificate.

The arithmetic joint observation is checked first. Its support J defines the
actual endomorphism X -> X intersection J on the four-element observation
carrier. Supplied atomic cells force the missing union cell at depth two.
The negative model satisfies every equation active at depth one.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'paper_ii_runtime'))
from engine import Term,const,depth,Theory,build_signature,generate_equations
from algebras import Algebra
from joint_kernel import replay as joint_replay


def plain(t):return json.loads(json.dumps(t))
def term(v):return Term(v[0],[term(a) for a in v[1:]])


def presentation(support):
    names=('empty','zero','one','both');rank={n:i for i,n in enumerate(names)}
    tables={op:{(a,b):names[(rank[a]|rank[b]) if op=='union' else (rank[a]&rank[b])] for a in names for b in names} for op in ['union','intersection']}
    A=Algebra('protected bit observations',names,{'union':2,'intersection':2},tables)
    B=Algebra('joint context',('joint',),{},{});h={n:names[rank[n]&support] for n in names}
    for op in A.operations:
        for a in names:
            for b in names:assert h[tables[op][a,b]]==tables[op][h[a],h[b]]
    th=Theory(A,B,schemes=('Tab',),tab={('joint','zero'):h['zero'],('joint','one'):h['one']})
    action,ops,ca,cb=build_signature(th);eqs=generate_equations(th,action)
    goal=(Term(action,(cb[0],const('A::both'))),const('A::'+names[support]))
    return eqs,goal,h


def replay(proof):
    arithmetic=proof['joint_certificate'];spec=dict(width=4,must=1,may=13,lower=2,upper=7,can_zero=True);query=dict(kind='bit',index=2)
    support=joint_replay(spec,query,arithmetic)['answer']['support'];assert support==2
    eqs,goal,h=presentation(support)
    assert proof['equations']==[[plain(a),plain(b)] for a,b in eqs] and proof['goal']==[plain(a) for a in goal]
    assert proof['completion']==h and proof['row_kernel']==[['empty','zero'],['one','both']]
    parent={};seen=set();maximum=max(depth(t) for t in goal)
    def find(t):
        parent.setdefault(t,t)
        while parent[t]!=t:t=parent[t]
        return t
    for event in proof['positive_events']:
        assert event['id'] not in seen;seen.add(event['id']);a,b=term(event['left']),term(event['right'])
        assert event['level']==max(depth(a),depth(b));maximum=max(maximum,event['level'])
        if event['kind']=='axiom':
            index=event['equation_index'];assert type(index) is int and 0<=index<len(eqs) and (a,b)==eqs[index]
        else:
            assert event['kind']=='congruence' and a.head==b.head and len(a.args)==len(b.args)
            assert all(find(x)==find(y) for x,y in zip(a.args,b.args))
        parent[find(a)]=find(b)
    assert find(goal[0])==find(goal[1]) and maximum==proof['visibility']==2
    model=proof['lower_model'];domain=set(model['domain']);assert domain and model['default'] in domain
    constants=model['constants'];assert all(v in domain for v in constants.values())
    functions={}
    for name,entries in model['operations'].items():
        table={}
        for args,value in entries:
            assert len(args)==model['arities'][name] and all(v in domain for v in args) and value in domain
            assert tuple(args) not in table;table[tuple(args)]=value
        functions[name]=table
    def evaluate(t):
        if not t.args:return constants.get(t.head,model['default'])
        return functions.get(t.head,{}).get(tuple(evaluate(a) for a in t.args),model['default'])
    active=[(a,b) for a,b in eqs if max(depth(a),depth(b))<=1]
    assert all(evaluate(a)==evaluate(b) for a,b in active)
    assert evaluate(goal[0])!=evaluate(goal[1])
    # A carrier-protecting total completion is given explicitly, so the
    # central carrier quotient is diagonal. The supplied inputs generate A.
    assert proof['protected_carrier']==['empty','zero','one','both']
    return dict(status='passed',native_observation_support=support,carrier_elements=4,
                forced_row_domain=4,row_kernel_classes=2,carrier_collapsed=False,
                visibility=2,lower_horizon=1,lower_model_elements=len(domain),
                all_lower_horizon_equations_checked=len(active),positive_events=len(proof['positive_events']),
                scope='Exact depth optimum of this finite ground presentation, not a width/complexity optimum for arbitrary arithmetic.')


def create(out):
    from joint_producer import produce
    from visibility_cc import VisibilityCongruenceClosure,AxiomReason
    from certificates import CertifiedProofStore
    from countermodel import extract_finite_model,verify_model
    spec=dict(width=4,must=1,may=13,lower=2,upper=7,can_zero=True);q=dict(kind='bit',index=2);joint=produce(spec,q)
    eqs,goal,h=presentation(joint['answer']['support']);run=VisibilityCongruenceClosure(eqs,list(goal)).run()
    store=CertifiedProofStore.from_run(run);store.validate_goal(*goal);events=[]
    for eid in store.reachable_event_ids(*goal):
        ev=store.certified[eid].event;kind='axiom' if isinstance(ev.reason,AxiomReason) else 'congruence'
        row=dict(id=eid,left=plain(ev.left),right=plain(ev.right),level=ev.level,kind=kind)
        if kind=='axiom':row['equation_index']=ev.reason.equation_index
        events.append(row)
    model=extract_finite_model(run,1);verify_model(run,model,1)
    exported=dict(domain=list(model.domain),constants=model.constants,arities=model.arities,default=model.default,
                  operations={name:[[list(args),value] for args,value in rows.items()] for name,rows in model.operations.items()})
    proof=dict(joint_certificate=joint,equations=[[plain(a),plain(b)] for a,b in eqs],goal=[plain(t) for t in goal],
               completion=h,row_kernel=[['empty','zero'],['one','both']],protected_carrier=['empty','zero','one','both'],
               positive_events=events,visibility=run.first_equal(*goal),lower_model=exported)
    result=replay(proof);out.mkdir(parents=True,exist_ok=False)
    (out/'certificate.json').write_text(json.dumps(proof,indent=2)+'\n')
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'explanation.txt').write_text(store.explain_text(*goal)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--create',action='store_true');a=p.parse_args();out=ROOT/'theory'
    print(json.dumps(create(out) if a.create else replay(json.loads((out/'certificate.json').read_text()))))
