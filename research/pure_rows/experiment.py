"""Fresh finite development evidence: all 20 two-element unary/binary tables
and all 256 subsets of eight possible cells with two named operators (5120).
Duplicate occurrences and higher arities have separate named/seeded/test scopes.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import random
import sys
import time
from .checker import check, check_completion, explain
from .common import digest, encoded, need, write_json
from .fixtures import examples, make
from .producer import produce
from .reference import ground

PROTOCOL = dict(schema='qkf-pure-row-development-protocol-v1',
                exhaustive_two_element_tables=20, operators=2, subsets_per_table=256,
                exhaustive_cases=5120, seeded_cases=128, seed=3802026,
                named_cases=16, baseline_tree='27e9a7c456c928694eee808a8a6c59967b13bc9a',
                scope='development finite instances, not external holdout or universal formalization')


def cases():
    for name, p in examples():
        yield 'named', name, p
    possible = list(itertools.product(range(2), repeat=3))
    for arity in (1,2):
        for ti, table in enumerate(itertools.product(range(2), repeat=2**arity)):
            for mask in range(256):
                cells=[cell for i,cell in enumerate(possible) if mask & (1<<i)]
                yield 'exhaustive', f'arity{arity}_table{ti}_cells{mask}', make(2,[(arity,table)],2,cells)
    rng=random.Random(PROTOCOL['seed'])
    for i in range(PROTOCOL['seeded_cases']):
        n,nb=3,3
        ops=[(1,[rng.randrange(n) for _ in range(n)]),(2,[rng.randrange(n) for _ in range(n*n)])]
        cells=[(rng.randrange(nb),rng.randrange(n),rng.randrange(n)) for _ in range(rng.randrange(10))]
        bops=[(1,[rng.randrange(nb) for _ in range(nb)])]
        yield 'seeded',f'mixed_three_{i}',make(n,ops,nb,cells,bops)


def aggregate(records):
    counts = {};named = {};pairs = 0;protected = 0;external = 0;rounds = 0
    for family,name,result,proof_size in records:
        counts[family] = counts.get(family,0) + 1
        order_size = sum(len(b) for b in result['interface']['horizon2_partition'])
        pairs += order_size*(order_size-1)//2
        protected += int(result['carrier_protected'])
        external += sum(row['external_count'] for row in result['rows'])
        rounds += result['strict_feedback_rounds']
        if family=='named':
            named[name]=dict(carrier_partition=result['carrier_partition'],
                            strict_feedback_rounds=result['strict_feedback_rounds'],
                            N1=result['interface']['N1'],N2=result['interface']['N2'],
                            rows=result['rows'],certificate_bytes=proof_size)
    return dict(schema='qkf-pure-row-development-summary-v1',status='passed',
                presentations=sum(counts.values()),families=counts,
                unordered_interface_pairs_per_horizon=pairs,horizons_checked=[1,2],
                protected_presentations=protected,external_row_classes_total=external,
                strict_feedback_rounds_total=rounds,named_cases=named,
                semantic_scope='exact named interface; completion witnesses checked separately',
                new_java_execution=False,new_smt_execution=False,lean_checked=False)


def completion_examples(named):
    definitions=[('I_6_1_amplification',[0,1,2],[[0,0,0]]),
                 ('I_6_2_obstruction',[0,1,0,2],[[0,0,0]]),
                 ('I_6_3_external_completion',[0,1],[[0,1]]),
                 ('I_7_4_no_least_repair',[0,1,0,2],[[0,0,0]]),
                 ('I_7_4_no_least_repair',[0,1,1,2],[[0,1,2]]),
                 ('I_7_6_repair_kernel_gap',[0,1,0,2],[[0,1,2]])]
    out=[]
    for name,theta,rows in definitions:
        p=named[name]
        w=dict(schema='qkf-pure-row-completion-v1',input_sha256=digest(p),carrier_partition=theta,actions=rows)
        out.append(dict(name=name,input=p,witness=w,result=check_completion(p,w)))
    return out


def run(root: Path):
    root.mkdir(parents=True,exist_ok=False)
    write_json(root/'PROTOCOL.json',PROTOCOL)
    (root/'cases').mkdir()
    old_path=Path(__file__).resolve().parents[2]/'papers/paper_I/verification/verify_article.py'
    spec=importlib.util.spec_from_file_location('paper_I_experiment_reference',old_path)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    records=[];index=[];costs=[];named={};maxima=dict(events=0,work=0,rounds=0)
    start=time.perf_counter()
    for i,(family,name,p) in enumerate(cases()):
        r,c,diag=produce(p)
        need(c is not None and r['status']=='certified',f'unexpected unresolved case {name}: {r}')
        production_end=time.perf_counter()
        check(p,c)
        check_end=time.perf_counter()
        refs=[ground(p,h) for h in (1,2)]
        for h,ref in enumerate(refs):
            need(ref['partition']==c['levels'][h]['equality']['partition'],'typed-ground comparison mismatch: '+name)
        n,nb=len(p['carrier']['names']),len(p['operators']['names'])
        ops=[(op['arity'],op['table']) for op in p['carrier']['operations']]
        plabels,ptheta,ptraj,pdetails=old.structural_interface(n,ops,nb,p['cells'])
        need(list(plabels)==refs[1]['partition'] and old.blocks(ptheta)==r['carrier_partition'] and
             len(ptraj)-1==r['strict_feedback_rounds'],'preserved structural prototype mismatch: '+name)
        need(all(row['forced_domain']==out['forced_domain'] for row,out in zip(pdetails,r['rows'])),
             'preserved saturation prototype mismatch: '+name)
        reference_end=time.perf_counter()
        proof_size=len(encoded(c));path=f'cases/case-{i:05d}.json'
        write_json(root/path,dict(family=family,name=name,input=p,proof=c))
        index.append(dict(path=path,family=family,name=name,input_sha256=digest(p),certificate_bytes=proof_size,
                          reference_nodes=[ref['represented_nodes'] for ref in refs]))
        records.append((family,name,r,proof_size))
        costs.append(dict(name=name,production=diag,replay_seconds=check_end-production_end,
                          independent_reference_seconds=reference_end-check_end))
        for k,v in diag['work'].items():maxima[k]=max(maxima[k],v)
        if family=='named':named[name]=p
        if i%512==0:print(f'pure-row case {i}: {name}',file=sys.stderr,flush=True)
    summary=aggregate(records)
    need(summary['families']==dict(named=16,exhaustive=5120,seeded=128),'development denominator changed')
    write_json(root/'INDEX.json',index)
    write_json(root/'COMPLETIONS.json',completion_examples(named))
    failure=[];control=named['I_6_2_obstruction']
    for limits in [dict(max_events=0),dict(max_work=0),dict(max_rounds=0),dict(max_rounds=1)]:
        result,proof,diag=produce(control,limits)
        need(proof is None and result['status']=='budget_exhausted','budget issued partial success')
        failure.append(dict(limits=limits,result=result,diagnostics=diag))
    performance=dict(runtime=sys.version,elapsed_seconds=time.perf_counter()-start,
                     max_production_work=maxima,cases=costs,failure_controls=failure,
                     old_prototype_sha256=hashlib.sha256(old_path.read_bytes()).hexdigest())
    (root/'PERFORMANCE.json').write_text(json.dumps(performance,indent=2,allow_nan=False)+'\n')
    query_examples=[];obstruction=json.loads((root/'cases/case-00001.json').read_text())
    for left,right,h in [(0,2,1),(0,2,2),(1,3,2),(5,0,2)]:
        query_examples.append(explain(obstruction['input'],obstruction['proof'],left,right,h))
    write_json(root/'QUERIES.json',query_examples)
    write_json(root/'SUMMARY.json',summary)
    manifest={str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest()
              for f in sorted(root.rglob('*')) if f.is_file()}
    write_json(root/'MANIFEST.json',manifest)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    args=parser.parse_args();print(encoded(run(args.output)).decode())
