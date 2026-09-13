#!/usr/bin/env python3
"""Independent word-level regressions for new identities and original SSA.

Tests are bounded implementation checks; OBSERVER_PROOFS.md states all-width
proofs and each rule's width/shape conditions. No test result is used as a rule.
"""
import argparse
import collections
import itertools
import json
import pickle
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'dependencies'))
from regular_interfaces import order,KB
from prefix_masks import lower,Machine,supported,RUNS
from audit_fixed import validate_freeze
from check_semantics import word_values,accepted_outputs


def lemmas(operation):
    from observer_kernel import new_rule,constant
    from qkf_certifier.kernel import Z,T,W,C1
    counts=collections.Counter();templates=collections.Counter();refusals=[]
    x,y,n=('var',0),('var',1),('var',2)
    def check(rule,e,minimum=1,max_width=6,optional=False):
        try:rhs=new_rule(rule,e,minimum)
        except ValueError:
            if optional:return
            raise
        variables=sorted({t[1] for t in order(e,rhs) if t[0]=='var'})
        assert len(variables)<=2
        templates[rule]+=1
        for w in range(minimum,max_width+1):
            for inputs in itertools.product(range(1<<w),repeat=len(variables)):
                vals=[0]*6
                for index,v in zip(variables,inputs):vals[index]=v
                lhs=word_values(e,vals,w,operation)[e]
                actual=word_values(rhs,vals,w,operation)[rhs]
                if lhs!=actual:raise AssertionError((rule,e,rhs,w,vals,lhs,actual))
                counts[rule]+=1
    for p,c,reverse in itertools.product((0,1,6,7,8,9),(Z,C1),(False,True)):
        a,b=(c,W) if reverse else (W,c)
        check('width-comparison',('cmp'+str(p),a,b),1 if c==Z else 2,10)
    for e in [('countl_one',('clear_sign_bit',x)),('countl_zero',('set_sign_bit',x)),
              ('countr_one',('and',x,constant(-2))),('countr_zero',('or',x,C1))]:
        check('count-boundary-zero',e)
    for minimum,c,v in itertools.product(range(1,6),('countl_one','countl_zero','countr_one','countr_zero'),range(-17,18)):
        check('literal-count',(c,constant(v)),minimum,8,True)
    for v in range(-20,21):check('literal-not',('not',constant(v)),1,10)
    for minimum,op,a,b in itertools.product(range(1,5),tuple('cmp'+str(i) for i in range(10))+('umin','umax','smin','smax'),range(-5,6),range(-5,6)):
        check('literal-order',(op,constant(a),constant(b)),minimum,8,True)
    check('unsigned-unit-bound',('cmp6',x,C1))
    check('unsigned-unit-bound',('cmp8',C1,x))
    for c in [('clear_sign_bit',y),C1]:
        for args in ((x,c),(c,x)):
            check('unsigned-smax-threshold',('cmp6',x,('smax',*args)),1 if c!=C1 else 2,5)
    check('unit-right-shift',('lshr',C1,n))
    check('unit-right-shift',('ashr',C1,n),2)
    for op,c,reverse in itertools.product(('cmp0','cmp1'),('countl_one','countl_zero','countr_one','countr_zero'),(False,True)):
        a,b=(Z,(c,x)) if reverse else ((c,x),Z)
        check('count-zero-test',(op,a,b))
    for k in range(7):
        b=('sub',W,constant(k))
        check('terminal-window',('clear_low_bits',x,b),max(k,1),8)
    for op in ('clear_low_bits','umin','umax'):
        check('distribute-observer-select',(op,x,('select',('cmp0',y,Z),C1,y)),1,5)
    fused=('lshr',('set_high_bits',Z,('countl_one',('shl',x,n))),n)
    check('shifted-leading-mask',fused,1,7)
    # Missing width and syntax conditions must be rejected by the rule checker.
    for label,rule,e,minimum in [
        ('ashr_one_at_width_one','unit-right-shift',('ashr',C1,n),1),
        ('terminal_window_underflow','terminal-window',('clear_low_bits',x,('sub',W,constant(2))),1),
        ('literal_count_too_narrow','literal-count',('countl_one',constant(-5)),2),
        ('smax_negative_threshold','unsigned-smax-threshold',('cmp6',x,('smax',x,T)),2),
        ('different_shift_counts','shifted-leading-mask',('lshr',fused[1],y),1),
        ('nonzero_mask_base','shifted-leading-mask',('lshr',('set_high_bits',C1,fused[1][2]),n),1),
        ('width_vs_one_without_partition','width-comparison',('cmp0',W,C1),1),
    ]:
        try:new_rule(rule,e,minimum)
        except ValueError:refusals.append(label)
        else:raise AssertionError('invalid rule premises accepted: '+label)
    # Show that two omitted width guards would actually make the identity false.
    exposed=[]
    for label,rule,e,values in [
        ('ashr_one_width_one','unit-right-shift',('ashr',C1,n),[0,0,1,0,0,0]),
        ('window_wrap_width_one','terminal-window',('clear_low_bits',x,('sub',W,constant(2))),[1,0,0,0,0,0]),
    ]:
        rhs=new_rule(rule,e,2)
        assert word_values(e,values,1,operation)[e]!=word_values(rhs,values,1,operation)[rhs]
        exposed.append(label)
    return {'cases':sum(counts.values()),'by_rule':dict(counts),'templates':dict(templates),
            'invalid_premises_rejected':refusals,'width_guard_necessity_witnesses':exposed,
            'shifted_mask_exhaustive_widths':list(range(1,8)),
            'scope':'All input words for the listed instances, including oversized shifts. Not an all-width proof.'}


def corpus(out,operation,evaluate,parse_bundle):
    with (out/'local_cache.pkl').open('rb') as f:items=pickle.load(f)
    items=[x for x in items if x['record']['role']=='component']
    records=[];total=path_cases=0
    for item in items:
        r=item['record'];expr=item['observed'];fs=parse_bundle(item['bundle']);cases=paths=0
        changed=bool(item['observer_trace'])
        # Enumerate accepting paths for all seven Umin components, including nested observers.
        machine=Machine(expr,'umin') if r['operator']=='KnownBits_Umin' and supported(expr) else None
        for w in (2,3):
            for rows in itertools.product(KB,repeat=2*w):
                vals=tuple(sum(rows[2*j+i//2][i%2]<<j for j in range(w)) for i in range(4))
                source=evaluate(fs,[vals[:2],vals[2:]],w,r['entry'])
                observed=word_values(expr,(*vals,0,0),w,operation)[expr]
                assert source==observed,(r['operator'],r['entry'],w,vals,source,observed)
                cases+=1
                if machine is not None:
                    accepted,_=accepted_outputs(machine,(*vals,0,0),w)
                    assert accepted=={(*source,0):1},(r['entry'],w,vals,source,accepted)
                    paths+=1
        total+=cases;path_cases+=paths
        records.append({'operator':r['operator'],'entry':r['entry'],'observer_trace_nonempty':changed,
                        'word_cases':cases,'all_accepting_path_cases':paths})
        if r['operator']=='KnownBits_Umin':print(r['operator'],r['entry'],'source and accepting paths PASS',flush=True)
    return {'components':len(items),'components_changed':sum(x['observer_trace_nonempty'] for x in records),
            'word_cases':total,'umin_all_accepting_path_cases':path_cases,'widths':[2,3],'records':records}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--repo',type=Path,required=True)
    ap.add_argument('--results',type=Path,default=ROOT/'results');ap.add_argument('--lemmas-only',action='store_true')
    args=ap.parse_args();repo=args.repo.resolve();validate_freeze(repo)
    sys.path[:0]=[str(repo/'src'),str(repo/'tests')]
    from word_oracle import operation,evaluate
    from qkf_certifier.frontend import parse_bundle
    start=time.perf_counter();result={'status':'PASS','lemmas':lemmas(operation)}
    print('Observer lemma implementation checks PASS',flush=True)
    if not args.lemmas_only:result['corpus']=corpus(args.results,operation,evaluate,parse_bundle)
    result['seconds']=time.perf_counter()-start;args.results.mkdir(exist_ok=True,parents=True)
    name='lemmas.json' if args.lemmas_only else 'semantics.json'
    (args.results/name).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='corpus'},indent=2))


if __name__=='__main__':main()
