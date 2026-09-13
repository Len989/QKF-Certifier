"""Check main evidence, inherited bytes, source provenance and exact denominators."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent


def read(name):return json.loads((ROOT/name).read_text())


def audit():
    if sys.flags.optimize:raise ValueError('Use ordinary Python with assertions enabled')
    from run_step import block_search,sha,SEARCH
    block_search()
    from freeze_step import verify
    from universal_kernel import replay
    from universal_api import CheckedUpperContract
    integrity=verify()
    if integrity!=dict(inherited_files=343,frozen_files=428):raise ValueError('Version membership')
    source=(ROOT/'baseline/source/IntegerStamp.java').read_text()
    base='results/main/universal_upper/'
    producer=read(base+'producer.json');strict=read(base+'replay.json');certificate=read(base+'certificate.json')
    verified=replay(source,certificate);checked=CheckedUpperContract(source,certificate)
    if producer['status']!='certificate_produced' or strict['status']!=verified['status']:raise ValueError('Main proof status')
    if producer['certificate_sha256']!=sha(ROOT/base/'certificate.json') or strict['certificate_sha256']!=producer['certificate_sha256']:raise ValueError('Main certificate link')
    if producer['certificate_bytes']!=(ROOT/base/'certificate.json').stat().st_size:raise ValueError('Certificate size')
    if strict['verification']!=verified or strict['search_modules_loaded']!=[]:raise ValueError('Strict proof record')
    if producer['source_sha256']!=verified['source_sha256']:raise ValueError('Source provenance')
    semantic=read('validation/semantics_v2/results.json');negative=read('validation/certificates_v1/results.json')
    if semantic['status']!='passed' or negative['status']!='passed' or semantic['failures']:raise ValueError('Validation failure')
    if semantic['exhaustive_upper_inputs']!=111972 or semantic['java_calls']!=114040 or semantic['joint_refinement_inputs']!=24174:raise ValueError('Semantic denominator')
    if sum(x['abstract_inputs'] for x in semantic['exhaustive'])!=111972 or sum(x['abstract_inputs'] for x in semantic['wide'])!=2160:raise ValueError('Width accounting')
    if negative['negative_checks']!=len(negative['rejections']) or negative['negative_checks']!=23 or negative['source_mutants']!=5 or negative['concrete_mutant_witnesses']!=5:raise ValueError('Mutation denominator')
    if len(negative['source_variants'])!=2 or any(x['status']!='proved_universal_upper_contract' for x in negative['source_variants']):raise ValueError('Source variants')
    for variant in negative['source_variants']:
        path='validation/certificates_v1/'+variant['name']
        result=replay((ROOT/(path+'.java')).read_text(),read(path+'_certificate.json'))
        if result['sweep']['states']!=variant['sweep_states']:raise ValueError('Variant certificate')
    samples=sorted((ROOT/'validation/semantics_v2').glob('sample_*.json'))
    if len(samples)!=strict['specialized_instances'] or len(samples)!=18:raise ValueError('Specialization denominator')
    for path,r in zip(samples,strict['instances']):
        instance=json.loads(path.read_text())['instance']
        if r['file']!=path.name or r['sha256']!=sha(path) or r['result']!=checked.verify_instance(instance['spec'],instance):raise ValueError('Specialization provenance')
    coverage={};source_word=0
    for mode,expect in [('control',['or']),('joint',['and','or'])]:
        summary=read('results/main/graal_regression/'+mode+'/summary.json');rows=summary['records']
        if summary['selected']!=5 or [r['operation'] for r in rows]!=['and','or','xor','add','sub']:raise ValueError('Graal selection')
        proved=[]
        for row in rows:
            if row['status']=='proved_source_observation_and_whole_word_ssa':
                if row['replay']['search_modules_loaded'] or row['word']['replay']['search_modules_loaded']:raise ValueError('Graal strict replay used search')
                directory=ROOT/'results/main/graal_regression'/mode/row['operation']
                source_hash=sha(directory/'source_certificate.json')
                word_hash=sha(directory/'word/certificates'/(row['operation'].capitalize()+'.json'))
                if source_hash!=row['source']['source_certificate_sha256'] or source_hash!=row['replay']['source_certificate_sha256']:raise ValueError('Graal source certificate hash')
                if word_hash!=row['word']['producer']['certificate_sha256'] or word_hash!=row['replay']['word_certificate_sha256']:raise ValueError('Graal word certificate hash')
                proved.append(row['operation']);source_word+=1
            elif row['status']!='adapter_unsupported':raise ValueError('Unreported Graal failure')
        if proved!=expect:raise ValueError('Graal regression changed')
        coverage[mode]=dict(proved=len(proved),selected=5,operations=proved)
    main=read('results/main/results.json')
    if main['status']!='completed' or main['integrity']!=integrity:raise ValueError('Main run completion')
    loaded=sorted(n for n in sys.modules if n.split('.')[0] in SEARCH)
    if loaded:raise ValueError('Audit loaded proof search')
    return dict(status='passed',integrity=integrity,universal_status=verified['status'],
                universal_certificate_bytes=producer['certificate_bytes'],sweep=verified['sweep'],
                order_total_preorders=verified['order']['total_preorders'],order_admitted_cases=verified['order']['admitted_cases'],
                semantic_inputs=dict(exhaustive_upper=111972,wide_upper=2160,native_java=114040,exact_joint_ranges=24174),
                negative_checks=23,source_mutants_with_concrete_witnesses=5,source_variants=2,
                strict_specializations=18,graal_coverage=coverage,graal_source_word_replays=source_word,
                historical_NiceToMeetYou=dict(whole='11/39',components='104/411'),
                full_create='not proved; incompatible temporary masks and lower/stabilization stages remain outside this contract',
                search_modules_loaded=loaded)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'audit/AUDIT.json');a=p.parse_args()
    result=audit();a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result))
