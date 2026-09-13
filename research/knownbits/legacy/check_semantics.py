"""Independent finite-word checks of the new mask and branch mechanisms."""
from pathlib import Path
from functools import lru_cache
import argparse,itertools,json,random,time
from common import ROOT,BASE,setup,check_baseline,save

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,required=True);a=ap.parse_args();repo=setup(a.repo)
    from qkf_certifier.kernel import Z,T,W,TRUE,FALSE,at,digest
    from qkf_certifier.frontend import parse_bundle
    from regular_interfaces import tree
    from word_oracle import operation,evaluate,kbwords
    from mask_observers import mask,rewrite,bounded,replay
    from branch_kernel import (atoms,bool_value,consequence,specialize,guard,first_select,GuardMachine)
    started=time.perf_counter();rng=random.Random(20260912)
    def evaluator(values,w):
        @lru_cache(None)
        def ev(e):
            op=e[0]
            if op=='var':return values[e[1]]
            if e==Z:return 0
            if e==T:return (1<<w)-1
            if e==W:return w
            if e in (TRUE,FALSE):return e==TRUE
            if op=='const':return e[1]&((1<<w)-1)
            xs=[ev(c) for c in e[1:]]
            if op=='pair':return tuple(xs)
            if op=='not':return xs[0]^((1<<w)-1)
            if op.startswith('cmp'):return operation('cmp',xs,int(op[3:]),w)
            return operation(op,xs,None,w)
        return ev
    x=('var',0);y=('var',1);p=('cmp6',x,y);programs=[]
    for family in ['countl','countr']:
        c=(family+'_one',x);d=(family+'_zero',y)
        for n in [c,('sub',W,c),('sub',W,('sub',W,c)),('umin',c,d),('umax',c,d),('select',p,c,d),
                  ('umin',('sub',W,c),('sub',W,d)),('select',p,('sub',W,c),('sub',W,d)),Z,W,('const',1)]:
            for side in ['low','high']:
                try:m=mask(side,n,1)
                except ValueError:continue
                programs.append((side,n,m))
    programs=list(dict.fromkeys(programs));mask_cases=0
    for w in range(1,7):
        for xv,yv in itertools.product(range(1<<w),repeat=2):
            ev=evaluator([xv,yv],w)
            for side,n,m in programs:
                count=ev(n);assert 0<=count<=w
                expect=operation('set_'+side+'_bits',[0,count],None,w)
                assert ev(m)==expect,(w,xv,yv,side,n,m)
                mask_cases+=1
                # Payloads cover zero/all bits and independent data patterns.
                for verb in ['set','clear']:
                    source=(verb+'_'+side+'_bits',('xor',x,y),n)
                    translated=rewrite(source,1)
                    assert ev(source)==ev(translated),(w,xv,yv,source,translated)
                    mask_cases+=1
    rejected=[]
    for label,n,minw in [('unbounded_word',x,2),('width_minus_unbounded',('sub',W,x),2),
                         ('count_sum',('add',('countl_one',x),('countl_one',y)),2),
                         ('negative_literal',('const',-2),2),('literal_above_minimum',('const',3),2),
                         ('signed_count_minimum',('smin',('countl_zero',x),('countl_zero',y)),2),
                         ('nonpositive_minimum',('countl_one',x),0)]:
        assert not bounded(n,minw)
        try:mask('high',n,minw)
        except ValueError:rejected.append(label)
        else:raise AssertionError('unjustified bound accepted')
    try:mask('low',('countl_one',x),2)
    except ValueError:rejected.append('unmatched_count_orientation')
    else:raise AssertionError('opposite-end count accepted')
    # Concrete reason the bound is necessary: w=2, arbitrary n=3.
    lhs=operation('clear_low_bits',[3,(2-3)&3],None,2)
    rhs=3&operation('set_high_bits',[0,3],None,2)
    assert lhs!=rhs
    save(ROOT/'results/mask_validation.json',{'status':'passed','grammar_observations':len(programs),'word_cases':mask_cases,'exhaustive_widths':list(range(1,7)),
        'rejected_missing_premises':rejected,'unbounded_complement_counterexample':{'width':2,'payload':3,'count':3,'original_output':lhs,'invalid_rewrite_output':rhs}})
    print('mask validation',mask_cases,flush=True)
    # Check bit-parallel propositional consequence against explicit valuations.
    aa=[('cmp0',('var',0),('const',i)) for i in range(8)]
    def formula(depth):
        if depth==0 or rng.random()<.3:return rng.choice(aa+[TRUE,FALSE])
        return (rng.choice(['booland','boolor','boolxor']),formula(depth-1),formula(depth-1))
    bool_cases=0
    for _ in range(512):
        path=tuple((formula(2),bool(rng.randrange(2))) for _ in range(rng.randrange(5)));q=formula(3)
        universe=atoms(q)
        for c,_ in path:universe|=atoms(c)
        universe=sorted(universe,key=repr);answers=[]
        for bits in itertools.product([False,True],repeat=len(universe)):
            v=dict(zip(universe,bits))
            if all(bool_value(c,v)==truth for c,truth in path):answers.append(bool_value(q,v))
        expected='empty' if not answers else True if all(answers) else False if not any(answers) else None
        assert consequence(path,q)==expected,(path,q)
        bool_cases+=1
    save(ROOT/'results/propositional_validation.json',{'status':'passed','formulas_checked_against_all_valuations':bool_cases,'max_atoms':8,'seed':20260912})
    print('propositional validation',bool_cases,flush=True)
    records=[]
    for case in json.loads((BASE/'CASES.json').read_text()):
        op=case['case'];data=json.loads((ROOT/'results/composed/expressions'/(op+'.json')).read_text());root=tree(data['observed'])
        old=tree(json.loads((BASE/'results/expressions'/(op+'.json')).read_text())['observed'])
        replay(old,data['mask_trace'],root,2)
        fs=parse_bundle({'program':(BASE/case['program']).read_text()});leaves=[]
        def partition(path,depth=0):
            if consequence(path,TRUE)=='empty':return
            e=specialize(root,path);where=first_select(e)
            if where is None or depth==24:leaves.append((path,guard(path),e));return
            p=at(e,where)[1];partition(path+((p,True),),depth+1);partition(path+((p,False),),depth+1)
        partition(());abstract=wide=0
        for w in [2,3,4,8,16,32,64]:
            if w<=4:inputs=[ka+kb for ka,kb in itertools.product(kbwords(w),repeat=2)]
            else:
                inputs=[]
                for _ in range(256):
                    z1=rng.getrandbits(w);o1=rng.getrandbits(w)&~z1;z2=rng.getrandbits(w);o2=rng.getrandbits(w)&~z2
                    inputs.append((z1,o1,z2,o2))
            for v in inputs:
                ev=evaluator(v,w);expected=evaluate(fs,[v[:2],v[2:]],w)
                assert ev(root)==expected,('mask/source discrepancy',op,w,v)
                matches=0
                for path,g,e in leaves:
                    if ev(g):
                        matches+=1;assert ev(e)==expected,('conditional specialization discrepancy',op,w,v,path)
                assert matches==1,('nonexhaustive/overlapping partition',op,w,v,matches)
            if w<=4:abstract+=len(inputs)
            else:wide+=len(inputs)
        row={'case':op,'status':'passed','full_abstract_pairs_width_2_to_4':abstract,'wider_pairs':wide,'partition_leaves':len(leaves)};records.append(row)
        save(ROOT/'results/source_semantics.partial.json',records);print(op,abstract,wide,'partition and source checked',flush=True)
    result={'status':'passed','records':records,'totals':{'full_abstract_pairs_width_2_to_4':sum(x['full_abstract_pairs_width_2_to_4'] for x in records),'wider_pairs':sum(x['wider_pairs'] for x in records)},'seed':20260912,'seconds':time.perf_counter()-started,'baseline_integrity':check_baseline(repo),
            'scope':'Finite-word validation of new normalization and source-derived case specialization. All-width soundness follows from checked rewrites and conditional invariants, with a trusted Python kernel.'}
    save(ROOT/'results/source_semantics.json',result)
if __name__=='__main__':main()
