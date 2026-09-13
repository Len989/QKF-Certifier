"""Audit retained evidence, source provenance, exact denominators and strict replay."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def read(n):return json.loads((ROOT/n).read_text())
def audit():
    from freeze_step import verify,sha
    from lower_kernel import replay
    from lower_api import CheckedLowerContract
    integrity=verify();main=read('results/main/results.json');producer=read('results/main/producer.json');c=read('results/main/certificate.json')
    source=(ROOT/'previous/baseline/source/IntegerStamp.java').read_text();proof=replay(source,c)
    saved=read('results/main/replay/lower_replay.json');expected={**proof,'search_modules_loaded':[]}
    if saved!=expected or main['status']!='completed' or main['integrity']!=integrity:raise ValueError('Main evidence')
    if producer['file_sha256']!=sha(ROOT/'results/main/certificate.json') or producer['certificate_bytes']!=(ROOT/'results/main/certificate.json').stat().st_size:raise ValueError('Producer binding')
    sem=read('validation/semantics/results.json');neg=read('validation/proofs/results.json')
    if sem['status']!='passed' or sem['failures'] or neg['status']!='passed':raise ValueError('Validation status')
    if sem['counts']!={k:sum(r[k] for r in sem['groups']) for k in sem['counts']}:raise ValueError('Denominator accounting')
    if sem['counts']['inputs']!=159398 or sem['counts']['java_calls']!=114044 or neg['certificate_corruptions']!=20 or len(neg['native_faulty_mutants'])!=5:raise ValueError('Exact validation denominators')
    if len(neg['positive_source_variants'])!=3 or neg['strategy_limitation']['finite_failures']:raise ValueError('Variant accounting')
    api=CheckedLowerContract(source,c);samples=sorted((ROOT/'validation/semantics').glob('sample_*.json'))
    for p in samples:
        s=json.loads(p.read_text());api.verify_instance(s['spec'],s['record'])
    chain=read('results/main/replay/results.json')
    if chain['status']!='passed' or chain['fresh_proof_processes']!=7:raise ValueError('Inherited strict proof chain')
    loaded=[n for n in sys.modules if any(t in n for t in ['producer','z3','pysmt'])]
    if loaded:raise ValueError('Audit imported search')
    return dict(status='passed',integrity=integrity,certificate_bytes=producer['certificate_bytes'],source_sha256=sha(ROOT/'previous/baseline/source/IntegerStamp.java'),
                universal_status=proof['status'],successor=proof['successor'],sweep_states=proof['sweep']['states'],outer=proof['outer'],semantics=sem['counts'],
                checked_saved_specializations=len(samples),certificate_corruptions=20,faulty_native_mutants=5,positive_variants=3,
                fresh_proof_processes=7,graal='control 1/5; joint 2/5 unchanged',NiceToMeetYou='historical 11/39 whole; 104/411 components',full_create='not proved',search_modules_loaded=[])
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'audit/AUDIT.json');a=p.parse_args();r=audit();a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
    print(json.dumps(r))
