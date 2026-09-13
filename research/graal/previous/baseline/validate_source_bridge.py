"""Independent Java execution, projection tests, scoped and source mutations."""
import copy,itertools,json,random,re,sys,time
from pathlib import Path
from joint_producer import produce
from joint_kernel import replay
from source_producer import produce_source
from source_kernel import replay_source,body
from hull_kernel import replay_hull
from native_java import evaluate
from validate_joint import masks
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'core'))
import environment
from qkf_certifier.frontend import parse_bundle
from word_oracle import evaluate as evaluate_ssa


def stamp(line,width):
    if not line.startswith('OK '):raise ValueError('Java source failed: '+line)
    _,low,high,must,may,zero=line.split();m=(1<<width)-1
    return dict(width=width,lower=int(low),upper=int(high),must=int(must,16)&m,may=int(may,16)&m,can_zero=bool(int(zero)))


def included(observation,destination):
    if observation['count']==0:return True
    return (destination['lower']<=observation['lower'] and observation['upper']<=destination['upper']
            and observation['must']&destination['must']==destination['must']
            and observation['may']&~destination['may']==0 and (destination['can_zero'] or not observation['zero']))


def observation(spec):return replay(spec,{'kind':'summary'},produce(spec,{'kind':'summary'}))['answer']


def run(out):
    out.mkdir(parents=True,exist_ok=False);start=time.perf_counter();rng=random.Random(20260913);records=[];source_errors=[];mismatches=[];saved=[]
    for w in [1,2,3,4,8,16,32,64]:
        s=1<<(w-1);m=(1<<w)-1;specs=[]
        if w<=4:
            for must,may in masks(w):
                for low in range(-s,s):
                    for high in range(low,s):
                        for zero in [False,True]:specs.append(dict(width=w,must=must,may=may,lower=low,upper=high,can_zero=zero))
        else:
            for _ in range(256):
                may=rng.getrandbits(w);must=rng.getrandbits(w)&may;low,high=sorted([rng.randrange(-s,s),rng.randrange(-s,s)])
                specs.append(dict(width=w,must=must,may=may,lower=low,upper=high,can_zero=bool(rng.randrange(2))))
            for _ in range(64):
                may=rng.getrandbits(w);must=rng.getrandbits(w)&may
                low=(must|s)-(1<<w) if may&s else must
                high=may-(1<<w) if must&s else may&~s
                specs.append(dict(width=w,must=must,may=may,lower=rng.randrange(-s,low+1),upper=rng.randrange(high,s),can_zero=True))
        lines=[f'create {w} {a["lower"]} {a["upper"]} {a["must"]:x} {a["may"]:x} {int(a["can_zero"])}' for a in specs]
        outputs=evaluate(lines);hulls=0;equivalences=0
        for i,(spec,line) in enumerate(zip(specs,outputs)):
            if not line.startswith('OK '):source_errors.append(dict(spec=spec,line=line));continue
            result=stamp(line,w);before=observation(spec);after=observation(result)
            if not(included(before,result) and included(after,spec)):
                mismatches.append(dict(spec=spec,java=line,before=before,after=after));continue
            equivalences+=1
            minimum=(spec['must']|s)-(1<<w) if spec['may']&s else spec['must']
            maximum=spec['may']-(1<<w) if spec['must']&s else spec['may']&~s
            if spec['can_zero'] and spec['lower']<=minimum and spec['upper']>=maximum:
                assert (result['must'],result['may'],result['lower'],result['upper'])==(spec['must'],spec['may'],minimum,maximum)
                hulls+=1
            if w in [4,8,64] and i in [0,len(specs)-1]:
                saved.append(dict(spec=spec,java_output=line,output_spec=result,
                                  input_certificate=produce(spec,{'kind':'summary'}),output_certificate=produce(result,{'kind':'summary'})))
        records.append(dict(width=w,source_calls=len(specs),full_carrier_equivalences=equivalences,hull_specializations=hulls));print('create',w,records[-1],flush=True)
    projection=[]
    for op in ['and','or']:
        source=(ROOT/f'core/fixtures/corpus/{op.capitalize()}/solution.mlir').read_text();fs=parse_bundle({'program':source})
        for w in [1,2,3,4,8,16,32,64]:
            mask=(1<<w)-1
            if w<=4:
                pairs=[(mask^may,must) for must,may in masks(w)];inputs=[(*a,*b) for a,b in itertools.product(pairs,repeat=2)]
            else:
                inputs=[]
                for _ in range(320):
                    values=[]
                    for _ in range(2):
                        may=rng.getrandbits(w);must=rng.getrandbits(w)&may;values.extend([mask^may,must])
                    inputs.append(tuple(values))
            lines=[f'{op} {w} '+ ' '.join(f'{x:x}' for x in values) for values in inputs];outputs=evaluate(lines)
            for values,line in zip(inputs,outputs):
                native=stamp(line,w);expected=(mask^native['may'],native['must'])
                assert evaluate_ssa(fs,[values[:2],values[2:]],w)==expected,(op,w,values,line)
            projection.append(dict(operation=op,width=w,checks=len(inputs)));print('projection',op,w,len(inputs),flush=True)
    original=(ROOT/'source/IntegerStamp.java').read_text();certificate=produce_source(original,'and');replay_source(original,'and',certificate);negative=[]
    def reject(label,fn):
        try:fn()
        except (ValueError,TypeError,KeyError,IndexError):negative.append(label)
        else:raise AssertionError('accepted mutation: '+label)
    bad=copy.deepcopy(certificate);bad['hull_certificates'].pop();reject('missing reachable create proof',lambda:replay_source(original,'and',bad))
    bad=copy.deepcopy(certificate);bad['source_observation']['leaves'].pop();reject('missing source branch',lambda:replay_source(original,'and',bad))
    bad=copy.deepcopy(certificate);bad['hull_certificates'][0]['guards']=[];reject('removed source guards',lambda:replay_source(original,'and',bad))
    bad=copy.deepcopy(certificate);bad['hull_certificates'][0]['prefix_rows'][0]['bounded_must']=1;reject('false prefix induction cell',lambda:replay_source(original,'and',bad))
    bad=copy.deepcopy(certificate);bad['hull_certificates'][0]['native_steps'].pop();reject('incomplete native derivation',lambda:replay_source(original,'and',bad))
    p=copy.deepcopy(certificate['hull_certificates'][0]);p['can_zero']=False
    reject('zero permission removed',lambda:replay_hull(original,p['cube'],p['lower'],p['upper'],False,p['guards'],p))
    changed=original.replace('ITERATION_LIMIT = 3;','ITERATION_LIMIT = 1;');assert changed!=original
    reject('shortened source stabilization budget',lambda:replay_source(changed,'and',certificate))
    changed=original.replace('(value | bit) <= bound','(value | bit) >= bound');assert changed!=original
    reject('changed native loop condition',lambda:replay_source(changed,'and',certificate))
    names,raw=body(original,'and');narrow=raw.replace('Math.min(upperBound, a.upperBound)','Math.min(upperBound, 0)');assert narrow!=raw
    reject('narrower unproved source range',lambda:produce_source(original.replace(raw,narrow,1),'and'))
    variants={}
    renamed=re.sub(r'\ba\b','left',raw);renamed=re.sub(r'\bb\b','right',renamed)
    getters=re.sub(r'\.(mustBeSet|mayBeSet|lowerBound|upperBound)\b(?!\s*\()',r'.\1()',raw)
    for name,text in [('local_renaming',renamed),('field_to_getter',getters)]:
        variant=original.replace(raw,text,1);proof=produce_source(variant,'and');checked=replay_source(variant,'and',proof)
        assert checked['expression']==certificate['source_observation']['expression'];variants[name]='passed'
    result=dict(status='passed' if not source_errors and not mismatches else 'discrepancies_preserved',create=records,
                source_calls=sum(r['source_calls'] for r in records),carrier_equivalences=sum(r['full_carrier_equivalences'] for r in records),
                hull_specializations=sum(r['hull_specializations'] for r in records),source_errors=source_errors,mismatches=mismatches,
                projection=projection,projection_checks=sum(r['checks'] for r in projection),negative_checks=negative,source_variants=variants,
                seconds=time.perf_counter()-start,scope='Concrete abstract inputs have whole-carrier certificates; universal AND uses the separate reviewed hull source lemma.')
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    for i,r in enumerate(saved):(out/f'carrier_certificate_{i}.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in {'create','projection','source_errors','mismatches'}}),flush=True)
    assert not source_errors and not mismatches,(source_errors[:1],mismatches[:1])


if __name__=='__main__':run(ROOT/'validation/source_bridge_v1')
