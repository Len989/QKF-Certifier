"""Certificate corruption, equivalent source variants and native mutant witnesses."""
import copy,hashlib,json,re,subprocess,time
from pathlib import Path
from lower_producer import produce
from lower_kernel import replay
from lower_api import CheckedLowerContract,sign_admissible
from lower_source import block_end
from probe_contract import masks,words
from native_lower import java
ROOT=Path(__file__).resolve().parent

def helper(source):
    start=source.index('private static long computeLowerBound(');return source[start:block_end(source,source.index('{',start))]
def replacement(source,old,new):
    body=helper(source)
    if body.count(old)!=1:raise ValueError('unique mutation target '+old)
    return source.replace(body,body.replace(old,new))

def native_variant(source,out,specs):
    out.mkdir(parents=True,exist_ok=False)
    base=(ROOT/'native/IntegerStamp.java').read_text();generated=base.replace(helper(base),helper(source));(out/'IntegerStamp.java').write_text(generated)
    command,env=java();jar=ROOT.parent/'qkf_graal_tools/ecj-3.42.0.jar'
    p=subprocess.run(command+['-jar',str(jar),'-17','-d',str(out/'classes'),str(out/'IntegerStamp.java')],env=env,text=True,capture_output=True,timeout=60)
    if p.returncode:raise ValueError(p.stderr)
    lines=[f'lower {s["width"]} {s["lower"]} {s["must"]:x} {s["may"]:x} {int(s["can_zero"])}' for s in specs]
    p=subprocess.run(command+['-da','-cp',str(out/'classes'),'IntegerStamp'],env=env,input='\n'.join(lines)+'\n',text=True,capture_output=True,timeout=60)
    if p.returncode:raise ValueError(p.stderr)
    values=p.stdout.splitlines()
    if len(values)!=len(specs):raise ValueError('mutant native output count')
    (out/'MANIFEST.json').write_text(json.dumps(dict(generated_sha256=hashlib.sha256(generated.encode()).hexdigest(),source_sha256=hashlib.sha256(source.encode()).hexdigest(),compiler_sha256=hashlib.sha256(jar.read_bytes()).hexdigest(),calls=len(specs),stderr=p.stderr),indent=2)+'\n')
    return values

def run():
    start=time.perf_counter();out=ROOT/'validation/proofs';out.mkdir(parents=True,exist_ok=False)
    source=(ROOT/'previous/baseline/source/IntegerStamp.java').read_text();c=produce(source)['certificate'];rejections=[]
    def negative(name,edit):
        bad=copy.deepcopy(c);edit(bad)
        try:replay(source,bad)
        except Exception as e:rejections.append(dict(name=name,reason=str(e)))
        else:raise ValueError('accepted corrupt certificate: '+name)
        (out/(name+'.json')).write_text(json.dumps(bad,indent=2)+'\n')
    negative('source_hash',lambda x:x['compiled_source'].__setitem__('source_sha256','0'*64))
    negative('source_program',lambda x:x['compiled_source']['carry_program'].__setitem__('first_action','or'))
    negative('remove_sign_precondition',lambda x:x['contract'].__setitem__('precondition','all compatible masks'))
    negative('false_exact_minimum',lambda x:x['contract'].__setitem__('precision','always exact minimum'))
    negative('sweep_atom',lambda x:x['sweep']['rows'][0]['supplied'][0].__setitem__(1,7))
    negative('sweep_edge',lambda x:x['sweep']['edges'][0].__setitem__(0,len(x['sweep']['states'])))
    negative('sweep_empty',lambda x:x['sweep'].__setitem__('initial',-1))
    negative('carry_bridge',lambda x:x['successor']['source_quotient'][0].__setitem__('next_quotient',0))
    negative('carry_atom',lambda x:x['successor']['rows'][0]['supplied'][0].__setitem__(1,3))
    negative('carry_forced_step',lambda x:x['successor']['rows'][0]['steps'][0].__setitem__('output',3))
    negative('carry_table',lambda x:x['successor']['rows'][0]['table'].__setitem__(0,3))
    negative('carry_kernel',lambda x:x['successor']['rows'][0].__setitem__('kernel',[[0,1,2,3]]))
    negative('carry_missing_row',lambda x:x['successor']['rows'].pop())
    negative('carry_missing_state',lambda x:x['successor']['states'].pop())
    negative('carry_missing_edge',lambda x:x['successor']['edges'][0].pop())
    negative('carry_wrong_edge',lambda x:x['successor']['edges'][0].__setitem__(0,len(x['successor']['states'])))
    negative('carry_wrong_boundary',lambda x:x['successor']['boundaries'][0][0].__setitem__('bad',True))
    negative('outer_count',lambda x:x['outer']['obligations'].__setitem__('admitted_orders',0))
    negative('outer_digest',lambda x:x['outer']['obligations'].__setitem__('obligations_sha256','0'*64))
    negative('outer_ir',lambda x:x['outer']['ir'].pop())
    variants=[]
    body=helper(source);renamed=body
    for a,b in [('bits','wordWidth'),('lowerBound','floorLimit'),('mustBeSet','requiredMask'),('mayBeSet','possibleMask'),('canBeZero','allowZero'),('newLowerBound','resultWord'),('optionalBits','freeMask'),('position','index'),('bit','cellBit'),('incremented','started'),('lowBit','firstOne')]:renamed=re.sub(r'\b'+a+r'\b',b,renamed)
    inputs=[('renamed_formals_and_locals',source.replace(body,renamed)),
            ('reversed_comparison_operands',replacement(source,'newLowerBound + bit <= lowerBound','lowerBound >= newLowerBound + bit')),
            ('zero_bit_add_equals_or',replacement(source,'newLowerBound |= bit;','newLowerBound += bit;'))]
    for name,s in inputs:
        p=produce(s);assert p['status']=='certificate_produced';r=replay(s,p['certificate'])
        (out/(name+'.java')).write_text(s);(out/(name+'_certificate.json')).write_text(json.dumps(p['certificate'],indent=2)+'\n')
        variants.append(dict(name=name,status=r['status'],carry_states=r['successor']['states']))
    specs=[];oracles=[]
    for w in range(1,5):
        sign=1<<(w-1)
        for m,a in masks(w):
            values=words(w,m,a)
            for low in range(-sign,sign):
                for zero in [False,True]:
                    s=dict(width=w,must=m,may=a,lower=low,upper=sign-1,can_zero=zero)
                    if sign_admissible(s):specs.append(s);oracles.append([v for v in values if v>=low and (zero or v!=0)])
    mutants=[('reversed_greedy_comparison','newLowerBound + bit <= lowerBound','newLowerBound + bit >= lowerBound'),
             ('first_optional_or','newLowerBound += bit;\n                            incremented = true;','newLowerBound |= bit;\n                            incremented = true;'),
             ('forbidden_cell_or','newLowerBound += bit;\n                            }\n                        } else if','newLowerBound |= bit;\n                            }\n                        } else if'),
             ('inverted_optional_branch','if (optionalBits == 0)','if (optionalBits != 0)'),
             ('inverted_zero_flag','newLowerBound == 0 && !canBeZero','newLowerBound == 0 && canBeZero')]
    outcomes=[]
    for name,a,b in mutants:
        s=replacement(source,a,b);(out/(name+'.java')).write_text(s)
        try:p=produce(s);reason=p['status']
        except Exception as e:reason=str(e)
        assert reason!='certificate_produced'
        outputs=native_variant(s,out/(name+'_native'),specs);witness=None
        for spec,feasible,line in zip(specs,oracles,outputs):
            try:v=int(line[3:]) if line.startswith('LO ') else None
            except ValueError:v=None
            if v is None or v<spec['lower'] or (feasible and v>min(feasible)):
                witness=dict(spec=spec,feasible_words=feasible,native_output=line,reason='native exception' if v is None else 'lower refinement loses a feasible word or moves backward');break
        assert witness is not None,name
        outcomes.append(dict(name=name,proof_rejection=reason,native_witness=witness,native_calls=len(specs)))
        print('native mutant rejected',name,witness['spec'],flush=True)
    # Strict predecessor + successor can be semantically valid but does not
    # satisfy the reused <= floor lemma. Preserve this strategy limitation.
    strict=replacement(source,'newLowerBound + bit <= lowerBound','newLowerBound + bit < lowerBound');attempt=produce(strict)
    (out/'strict_predecessor_variant.java').write_text(strict);(out/'strict_predecessor_attempt.json').write_text(json.dumps(attempt,indent=2)+'\n')
    strict_outputs=native_variant(strict,out/'strict_predecessor_native',specs);strict_failures=[]
    for s,feasible,line in zip(specs,oracles,strict_outputs):
        v=int(line[3:]) if line.startswith('LO ') else None
        if v is None or v<s['lower'] or feasible and v>min(feasible):strict_failures.append(dict(spec=s,output=line))
    assert attempt['status']=='sweep_counterexample' and not strict_failures
    api=CheckedLowerContract(source,c);spec=dict(width=8,must=0,may=5,lower=2,upper=127,can_zero=True);record=api.refine(spec);record['answer']['source_long_result']+=1
    try:api.verify_instance(spec,record)
    except ValueError:instance_rejection=True
    else:raise ValueError('accepted changed lower specialization')
    result=dict(status='passed',certificate_corruptions=len(rejections),rejections=rejections,positive_source_variants=variants,
                native_faulty_mutants=outcomes,native_mutant_calls=len(specs)*len(mutants),
                strategy_limitation=dict(variant='strict predecessor',proof_status=attempt['status'],native_cases=len(specs),finite_failures=strict_failures,
                    interpretation='A rejected intermediate lemma is not by itself a bug in the complete lower procedure. No all-width proof of this variant is claimed.'),
                changed_instance_rejected=instance_rejection,seconds=time.perf_counter()-start)
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['status','certificate_corruptions','native_mutant_calls','seconds']}))
if __name__=='__main__':run()
