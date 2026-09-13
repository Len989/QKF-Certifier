#!/usr/bin/env python3
"""Paper III checks against the exact public release; Python >=3.10, stdlib only."""
from pathlib import Path
import argparse,itertools as it,json,sys,subprocess,time,statistics,platform,hashlib
from collections import Counter
ROOT=Path(__file__).resolve().parent
COMMIT='f93561682319e8b911ed32c01583f2a496dc59fc'


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--repo',type=Path,required=True);args=ap.parse_args()
    repo=args.repo.resolve()
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    if actual!=COMMIT:raise SystemExit('Wrong source commit: '+actual)
    sys.path[:0]=[str(repo/'src'),str(repo/'tests')]
    from qkf_certifier import verify,check_certificate,inspect
    from qkf_certifier.kernel import RULES,KB,Z,T,W,C1,TRUE,FALSE,CONTRACT,apply_rule,at,replace,children,bit
    from qkf_certifier.frontend import expression,parse_bundle
    from qkf_certifier.certificate import SCHEMA
    from word_oracle import expr_value,kbwords
    from mutation_helpers import variants
    start=time.perf_counter()
    def bundle(name):
        d={'program':(repo/'examples'/'ntmy'/(name+'.mlir')).read_bytes().decode('utf-8')}
        if name=='xor':d['meet']=(repo/'examples'/'ntmy'/'meet.mlir').read_bytes().decode('utf-8')
        return d
    def metrics(e):
        ms=[metrics(e[i]) for i in children(e)]
        return (1+sum(x[0] for x in ms),int(e[0]=='add')+sum(x[1] for x in ms))
    def mu(e):return sum(metrics(e))
    examples={};certdir=ROOT/'certificates';certdir.mkdir(exist_ok=True)
    for name in ['and','or','xor']:
        b=bundle(name);result=verify(b,name);c=result['certificate']
        assert result['status']=='certified' and result['optimal']
        assert check_certificate(b,name,c)['status']=='certified'
        e=expression(parse_bundle(b),'solution');initial_mu=mu(e);mus=[initial_mu]
        for step in c['steps']:
            nxt=replace(e,step['path'],apply_rule(step['rule'],at(e,step['path'])))
            assert mu(nxt)<mu(e);e=nxt;mus.append(mu(e))
        info=inspect(b);timings={}
        for label,fn in [('verify',lambda:verify(b,name)),('check',lambda:check_certificate(b,name,c))]:
            samples=[]
            for _ in range(31):
                t=time.perf_counter();fn();samples.append((time.perf_counter()-t)*1000)
            timings[label]={'median_ms':statistics.median(samples),'min_ms':min(samples),'max_ms':max(samples),'repetitions':len(samples)}
        text=json.dumps(c,sort_keys=True,separators=(',',':'))+'\n';(certdir/(name+'.json')).write_text(text)
        examples[name]={'status':result['status'],'optimal':result['optimal'],'rewrite_steps':len(c['steps']),
                        'rules':dict(Counter(x['rule'] for x in c['steps'])),'semantic_signature':info['semantic_signature'],
                        'original_unique_nodes':info['original_unique_nodes'],'normalized_unique_nodes':info['normalized_unique_nodes'],
                        'expanded_tree_measure':mus,'certificate_bytes_compact':len(text.encode()),'source_hashes':c['sources'],'timings':timings}
    print('real examples, replay, and decreasing measure: PASS',flush=True)
    v=[('var',i) for i in range(4)]
    cases={
      'idempotent':('or',v[0],v[0]),'self-cancel':('sub',v[0],v[0]),'zero-and':('mul',v[0],Z),
      'ones-or':('or',v[0],T),'zero-identity':('add',Z,v[0]),'ones-and':('and',T,v[0]),
      'not-constant':('not',T),'not-not':('not',('not',v[0])),'disjoint-and':('and',v[0],v[1]),
      'disjoint-add':('add',v[0],v[1]),'clear-width':('clear_low_bits',v[0],W),
      'count-constant':('countr_zero',Z),'clear-zero-count':('clear_high_bits',v[0],Z),
      'set-zero-count':('set_low_bits',v[0],Z),'set-leading-included':('set_high_bits',('or',v[0],v[2]),('countl_one',v[0])),
      'umin-zero':('umin',Z,v[1]),'umax-ones':('umax',v[0],T),'remainder-zero':('urem',Z,v[0]),
      'urem-one':('urem',v[0],C1),'udiv-one':('udiv',v[0],C1),'count-bound':('cmp9',W,('countl_one',v[0])),
      'compare-reflexive':('cmp3',v[0],v[0]),'compare-unsigned-bound':('cmp6',Z,('or',v[0],C1)),
      'select-constant':('select',TRUE,v[0],v[1]),'select-same':('select',('cmp0',v[0],v[1]),v[2],v[2]),
      'bool-constant':('boolor',TRUE,('cmp0',v[0],v[1])),'set-low-one':('set_low_bits',Z,C1),
      'zero-shift':('ashr',Z,v[0]),'shift-zero-count':('shl',v[0],Z)}
    assert set(cases)==set(RULES) and len(RULES)==29
    comparisons=0
    for rule,e in cases.items():
        new=apply_rule(rule,e);assert mu(new)<mu(e)
        for width in [1,2,3]:
            for a,b in it.product(kbwords(width),repeat=2):
                assert expr_value(e,a+b,width)==expr_value(new,a+b,width),(rule,width,a,b)
                comparisons+=1
    print('29 rule witnesses and finite word semantics: PASS',flush=True)
    rows=list(it.product(KB,repeat=2))
    def gamma(k):return {x for x in (0,1) if not x&k[0] and x&k[1]==k[1]}
    minterms=[]
    for a,b in rows:
        terms=[v[i] if val else ('not',v[i]) for i,val in enumerate(a+b)]
        e=terms[0]
        for t in terms[1:]:e=('and',e,t)
        minterms.append(e)
    masks=set()
    for wanted in range(512):
        e=Z
        for i in range(9):
            if wanted>>i&1:e=('or',e,minterms[i])
        actual=sum(bit(e,a+b)<<i for i,(a,b) in enumerate(rows))
        assert actual==wanted;masks.add(actual)
    order=[(i,j) for i,(a,b) in enumerate(rows) for j,(c,d) in enumerate(rows) if gamma(a)<=gamma(c) and gamma(b)<=gamma(d)]
    classifications={}
    for name in ['and','or','xor']:
        exact=[{(x&y if name=='and' else x|y if name=='or' else x^y) for x,y in it.product(gamma(a),gamma(b))} for a,b in rows]
        sound=mono=0
        for outputs in it.product(KB,repeat=9):
            values=[gamma(k) for k in outputs]
            if all(e<=o for e,o in zip(exact,values)):
                sound+=1
                if all(values[i]<=values[j] for i,j in order):mono+=1
        assert (sound,mono)==((16,16) if name=='xor' else (64,26))
        classifications[name]={'sound_classes':sound,'monotone_sound_classes':mono}
    print('complete Boolean image and monotone sound class counts: PASS',flush=True)
    mutation_counts=Counter();mutation_per_target={};signature_counts={}
    for name in ['and','or','xor']:
        b=bundle(name);ms=variants(b['program']);per=Counter();signatures=set();coordinate_count=0
        for _,source in [('original',b['program']),*ms.items()]:
            sources={**b,'program':source};res=verify(sources,name)
            if _!='original':per[res['status']]+=1;mutation_counts[res['status']]+=1
            inf=inspect(sources)
            if inf['status']=='normalized' and inf.get('coordinatewise'):
                signatures.add(inf['semantic_signature']);coordinate_count+=1
        mutation_per_target[name]={'total':len(ms),'statuses':dict(per)}
        signature_counts[name]={'coordinatewise_candidates_including_original':coordinate_count,'distinct_signatures':len(signatures)}
    assert sum(mutation_counts.values())==680
    print('mutation verdicts and semantic classes: PASS',flush=True)
    def concrete(k,w):return {x for x in range(1<<w) if not x&k[0] and x&k[1]==k[1]}
    def best_add(a,b,w):
        mask=(1<<w)-1;values={(x+y)&mask for x,y in it.product(concrete(a,w),concrete(b,w))};z=o=mask
        for x in values:z&=mask^x;o&=x
        return z,o
    join=lambda a,b:(a[0]&b[0],a[1]&b[1])
    a,aa,b=(3,0),(0,3),(2,1)
    lhs=best_add(join(a,aa),b,2);rhs=join(best_add(a,b,2),best_add(aa,b,2))
    assert lhs==(0,0) and rhs==(2,0)
    # Generator composition counterexample (U=0, Z=1, U is greatest).
    def closure(pairs):
        out=set(pairs)
        while True:
            extra={(x&u,y&v) for x,y in out for u,v in out}
            if extra<=out:return out
            out|=extra
    def compose(R,S):return {(a,c) for a,b in R for bb,c in S if b==bb}
    G={(0,0)};H={(0,1),(1,0)}
    full=compose(closure(G),closure(H));naive=closure(compose(G,H));assert full=={(0,0),(0,1)} and naive=={(0,1)}
    result={'status':'PASS','software_commit':COMMIT,'software_version':'0.1.0a1','certificate_schema':SCHEMA,
            'semantic_contract':CONTRACT,'environment':{'python':platform.python_version(),'platform':platform.platform()},
            'examples':examples,'rule_witnesses':len(cases),'rule_semantics_comparisons':comparisons,
            'boolean_mask_image_size':len(masks),'raw_pair_class_count':len(masks)**2,'valid_output_class_count':3**9,
            'precision_classifications':classifications,'mutation_statuses':dict(mutation_counts),'mutation_per_target':mutation_per_target,
            'semantic_deduplication':signature_counts,'join_add_counterexample':{'width':2,'lhs':lhs,'rhs':rhs},
            'generator_composition_counterexample':{'G':sorted(G),'H':sorted(H),'full':sorted(full),'naive':sorted(naive)},
            'elapsed_seconds':round(time.perf_counter()-start,3),
            'scope':'Fresh finite evidence and implementation regression; general proofs are in the manuscript, not inferred from sampling.'}
    (ROOT/'release_results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':
    if not __debug__:raise SystemExit('Run without -O: assertions are required.')
    main()
