#!/usr/bin/env python3
"""Reproduce the finite examples in Paper II. Python >=3.10, standard library.
Run without -O: assertions are part of these research checks.
"""
from pathlib import Path
import sys, json, math, itertools, platform, time
from collections import deque
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'prototype'))
from engine import Term, const, depth, build_pool, close
from visibility_cc_fast import IncrementalVisibilityCC
from certificates import CertifiedProofStore
from countermodel import extract_finite_model, verify_model


def op(name,*args): return Term(name,args)
def power(f,k,t):
    for _ in range(k): t=op(f,t)
    return t

def norm(q,uf):
    blocks={}
    for t in q: blocks.setdefault(uf.find(t),[]).append(t.pretty())
    return tuple(sorted(tuple(sorted(v)) for v in blocks.values()))

def model_json(m):
    return {'domain':list(m.domain),'constants':m.constants,'default':m.default,
            'arities':m.arities,'operations':{f:[{'args':list(k),'value':v} for k,v in sorted(table.items())] for f,table in m.operations.items()}}

def ground_neighbors(t,E):
    for l,r in E:
        if t==l: yield r
        if t==r: yield l
    for i,a in enumerate(t.args):
        for b in ground_neighbors(a,E):
            yield Term(t.head,t.args[:i]+(b,)+t.args[i+1:])

def reachable(s,t,D,neighbors,size):
    if max(size(s),size(t))>D: return False
    seen={s};queue=deque([s])
    while queue:
        u=queue.popleft()
        if u==t: return True
        for v in neighbors(u):
            if size(v)<=D and v not in seen: seen.add(v);queue.append(v)
    return False

def verify_gaps():
    p,q,r=map(const,['p','q','r']);f=lambda t:op('f',t)
    E=[(p,f(f(r))),(q,f(f(r)))];s,t=f(p),f(q)
    run=IncrementalVisibilityCC(E,[s,t],horizon=3).run()
    store=CertifiedProofStore.from_run(run);store.validate_goal(s,t)
    assert run.first_equal(s,t)==store.max_level(s,t)==2
    assert not reachable(s,t,2,lambda u:ground_neighbors(u,E),depth)
    assert reachable(s,t,3,lambda u:ground_neighbors(u,E),depth)
    a=const('a');G={c:const('b_'+c) for c in 'pxyz'}
    def W(w,t=a):
        for c in reversed(w): t=op('alpha',G[c],t)
        return t
    # At horizon 4 the only nontrivial universal instances have constant tails.
    E4=[(W(c,z),W('zzzz',z)) for c in 'xy' for z in [a,*G.values()]]
    s,t=W('px'),W('py')
    rr=IncrementalVisibilityCC(E4,[s,t],horizon=4).run()
    assert rr.first_equal(s,t)==4
    rules=[('x','zzzz'),('y','zzzz')]
    def neighbors(w):
        for l,r in rules:
            for u,v in [(l,r),(r,l)]:
                for i in range(len(w)-len(u)+1):
                    if w[i:i+len(u)]==u: yield w[:i]+v+w[i+len(u):]
    assert not reachable('px','py',4,neighbors,len)
    assert reachable('px','py',5,neighbors,len)
    return {'ground':{'congruence_depth':2,'rewrite_depth':3},'action_chains':{'congruence_depth':4,'rewrite_depth':5}}

def verify_catalan():
    counts={};flattened=0;thresholds=0
    for h in range(1,6):
        profiles=[a for a in itertools.combinations_with_replacement(range(h+1),h) if all(i<=v for i,v in enumerate(a))]
        assert len(profiles)==math.comb(2*h+2,h+1)//(h+2)
        for index,a in enumerate(profiles):
            E=[];C=[]
            for i,v in enumerate(a):
                if v>i:
                    p,q,r=[const(f'{x}{i}') for x in 'pqr'];C.extend([p,q,r])
                    E.extend([(power('f',i,p),power('f',v,r)),(power('f',i,q),power('f',v,r))])
            if not E or max(max(depth(l),depth(r)) for l,r in E)<h:
                u,v=const('u'),const('v');C.extend([u,v]);E.append((power('f',h,u),power('f',h,v)))
            pools={d:build_pool({'f':1},C,d,0) for d in range(h+1)}
            run=IncrementalVisibilityCC(E,pools[h],horizon=h).run()
            actual=tuple(run.stabilization_horizon(pools[d]) for d in range(h))
            assert actual==a,(h,a,actual)
            assert run.stabilization_horizon(pools[h])==h
            # Independent full bounded-universe closure at each threshold.
            for D in range(h+1):
                uf,_=close(pools[D],E,{'f':1})
                assert norm(pools[D],uf)==run.partition(pools[D],D)
                thresholds+=1
            if index in {0,len(profiles)//2,len(profiles)-1}:
                Eplus=E+[(s,t) for i,s in enumerate(pools[h]) for t in pools[h][i+1:] if run.exact_equal(s,t)]
                rp=IncrementalVisibilityCC(Eplus,pools[h],horizon=h).run()
                for d in range(h+1): assert rp.stabilization_horizon(pools[d])==d
                assert rp.partition(pools[h],h)==run.partition(pools[h],h)
                flattened+=1
        counts[str(h)]=len(profiles)
    return {'profiles_by_axiom_depth':counts,'profiles_total':sum(counts.values()),'bounded_partition_comparisons':thresholds,'flattening_examples':flattened}

def verify_shared_example():
    A=list(map(lambda i:const(str(i)),range(4)));b=const('b')
    F=[[0,2,0,0],[1,2,1,3],[0,2,2,0],[3,0,3,0]]
    f=lambda x,y:op('f',x,y);alpha=lambda x,y:op('alpha',x,y)
    R=[alpha(b,x) for x in A]
    native=[(f(A[i],A[j]),A[F[i][j]]) for i in range(4) for j in range(4)]
    observations=[(R[i],A[v]) for i,v in [(0,0),(2,2),(3,0)]]
    compat=[(alpha(b,f(A[i],A[j])),f(R[i],R[j])) for i in range(4) for j in range(4)]
    E=native+observations+compat;Q=A+R
    run=IncrementalVisibilityCC(E,Q,horizon=2).run();store=CertifiedProofStore.from_run(run)
    proofs=[]
    for s,t in [(A[0],A[2]),(R[1],A[0])]:
        store.validate_goal(s,t)
        assert store.max_level(s,t)==run.first_equal(s,t)==2
        proofs.append(store.explain_text(s,t))
    assert len(run.partition(Q,1))==5 and len(run.partition(Q,2))==3
    # Explicit typed five-element lower model, independently of closure.
    def low_eval(t):
        if not t.args: return t.head if t.head=='b' else int(t.head)
        vals=[low_eval(x) for x in t.args]
        if t.head=='f':
            i,j=vals;return F[i][j] if i<4 and j<4 else 0
        assert vals[0]=='b';return [0,4,2,0,0][vals[1]]
    assert all(low_eval(l)==low_eval(r) for l,r in E if max(depth(l),depth(r))<=1)
    assert low_eval(A[0])!=low_eval(A[2]) and low_eval(R[1])!=low_eval(A[0])
    quotient=[0,1,0,2];qF={}
    for i in range(4):
        for j in range(4):
            key=(quotient[i],quotient[j]);v=quotient[F[i][j]]
            assert key not in qF or qF[key]==v
            qF[key]=v
    def final_eval(t):
        if not t.args:return t.head if t.head=='b' else quotient[int(t.head)]
        vals=[final_eval(x) for x in t.args]
        return qF[tuple(vals)] if t.head=='f' else 0
    assert all(final_eval(l)==final_eval(r) for l,r in E)
    assert len({final_eval(t) for t in Q})==3
    low=extract_finite_model(run,1);verify_model(run,low,1)
    final=extract_finite_model(run,2);verify_model(run,final,2)
    data={'equations':[[l.pretty(),r.pretty()] for l,r in E],
          'partitions':{str(D):run.partition(Q,D) for D in [1,2]},
          'proofs':proofs,'dag_model_D1':model_json(low),'dag_model_D2':model_json(final),
          'typed_lower_model':{'carrier':[0,1,2,3,4],'operator':['b'],'native_table_on_0_to_3':F,'other_f_value':0,'row':[0,4,2,0,0]},
          'typed_full_model':{'carrier':[0,1,2],'quotient_map':quotient,'native_table':[[qF[(i,j)] for j in range(3)] for i in range(3)],'row':[0,0,0]}}
    (ROOT/'verification'/'shared_example_certificates.json').write_text(json.dumps(data,indent=2)+'\n')
    return {'N1':5,'N2':3,'exact_pair_depths':[2,2],'equations':len(E),'dag_nodes':len(run.nodes)}

def verify_square():
    C=[const('c0'),const('c1')];B=[const('b0'),const('b1')]
    a=lambda x,y:op('alpha',x,y);p=lambda x,y:op('plus',x,y)
    m=lambda x,y:op('times',x,y);n=lambda x:op('neg',x)
    base=[(p(C[x],C[y]),C[(x+y)%2]) for x in range(2) for y in range(2)]
    base += [(n(C[x]),C[x]) for x in range(2)]
    base += [(m(B[x],B[y]),B[x*y]) for x in range(2) for y in range(2)]
    compat=[(a(g,p(x,y)),p(a(g,x),a(g,y))) for g in B for x in C for y in C]
    compat += [(a(g,n(x)),n(a(g,x))) for g in B for x in C]
    ann=[(a(B[0],x),C[0]) for x in C]
    comp=[(a(m(g,h),x),a(g,a(h,x))) for g in B for h in B for x in C]
    ops={'plus':2,'times':2,'neg':1,'alpha':2}
    pools={d:build_pool(ops,C+B,d,0) for d in range(3)};Q=pools[1]
    rows=[];certificates=[]
    specs=[('Ann',0,0,0,(0,1),(44,44)),('Ann+Comp',0,1,0,(0,2),(44,43)),('Ann+R',1,0,0,(1,1),(26,26)),('Ann+R+Comp',1,1,0,(1,2),(26,25)),('Flip',0,0,1,(2,2),(42,25))]
    for name,R,Comp,Flip,profile,counts in specs:
        E=base+compat+([(a(g,C[x]),C[1-x]) for g in B for x in range(2)] if Flip else ann)+([(a(B[0],C[0]),C[1])] if R else [])+(comp if Comp else [])
        run=IncrementalVisibilityCC(E,Q,horizon=2).run()
        assert tuple(run.stabilization_horizon(q) for q in [C+B,Q])==profile
        assert tuple(len(run.partition(Q,D)) for D in [1,2])==counts
        for D in range(3):
            uf,_=close(pools[D],E,ops);active=[t for t in Q if depth(t)<=D]
            assert norm(active,uf)==run.partition(active,D),(name,D)
        models={}
        for D in range(3):
            model=extract_finite_model(run,D);verify_model(run,model,D);models[str(D)]=model_json(model)
        rows.append({'name':name,'profile':profile,'classes_D1_D2':counts,'equations':len(E),'dag_nodes':len(run.nodes)})
        certificates.append({'name':name,'equations':[[l.pretty(),r.pretty()] for l,r in E],'models':models,'query_partitions':{str(D):run.partition([t for t in Q if depth(t)<=D],D) for D in range(3)}})
    (ROOT/'verification'/'visibility_square_certificates.json').write_text(json.dumps(certificates,indent=2)+'\n')
    return {'bounded_universe_sizes':{str(d):len(v) for d,v in pools.items()},'cases':rows,'bounded_partition_comparisons':15}

def verify_empty():
    run=IncrementalVisibilityCC([],[],horizon=0).run()
    assert run.stabilization_horizon([])==0
    model=extract_finite_model(run,0);verify_model(run,model,0)
    assert len(model.domain)==1
    return {'empty_query_depth':0,'empty_active_model_domain_size':1}

def main():
    if not __debug__: raise SystemExit('Run without -O; assertions are required.')
    start=time.monotonic();results={'status':'RUNNING','python':platform.python_version()}
    for name,fn in [('resource_gaps',verify_gaps),('catalan',verify_catalan),('shared_action_example',verify_shared_example),('visibility_square',verify_square),('empty_input',verify_empty)]:
        results[name]=fn();print(name+': PASS',flush=True)
    results['status']='PASS';results['elapsed_seconds']=round(time.monotonic()-start,3)
    out=ROOT/'verification'/'results.json';out.write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results,indent=2))
if __name__=='__main__':main()
