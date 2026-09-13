"""Proof mutations, genuine source mutants and harmless source-form variants."""
import copy,json,re
from pathlib import Path
from source_contract import compile_source
from universal_producer import produce
from universal_kernel import replay
from universal_api import CheckedUpperContract,execute_concrete
from validate_semantics import masks,words,expected
ROOT=Path(__file__).resolve().parent


def run(out):
    out.mkdir(parents=True,exist_ok=False);source=(ROOT/'baseline/source/IntegerStamp.java').read_text()
    certificate=produce(source)['certificate'];rejections=[];mutants=[];variants=[]
    def reject(name,fn):
        try:fn()
        except (ValueError,AssertionError,KeyError,IndexError,TypeError) as error:
            rejections.append(dict(name=name,error=repr(error)))
        else:raise ValueError('Accepted corrupt evidence: '+name)
    changes=[
        ('missing supplied atom',lambda c:c['sweep_certificate']['rows'][0]['supplied'].pop()),
        ('false native supplied image',lambda c:c['sweep_certificate']['rows'][0]['supplied'][0].__setitem__(1,7)),
        ('missing forced row step',lambda c:c['sweep_certificate']['rows'][0]['steps'].pop()),
        ('invented row kernel',lambda c:c['sweep_certificate']['rows'][0].__setitem__('kernel',[[0,1,2,3,4,5,6,7]])),
        ('missing observation state',lambda c:c['sweep_certificate']['states'].pop()),
        ('missing bit-column transition',lambda c:c['sweep_certificate']['edges'][0].pop()),
        ('wrong transition target',lambda c:c['sweep_certificate']['edges'][0].__setitem__(0,48)),
        ('missing signed boundary',lambda c:c['sweep_certificate']['boundaries'][0].pop()),
        ('invented universal order coverage',lambda c:c['order_certificate'].__setitem__('total_preorders',47292)),
        ('changed order case stream',lambda c:c['order_certificate'].__setitem__('case_stream_sha256','0'*64)),
        ('expanded incompatible-mask contract',lambda c:c['contract'].__setitem__('masks','arbitrary masks'))]
    for name,change in changes:
        bad=copy.deepcopy(certificate);change(bad);reject(name,lambda bad=bad:replay(source,bad))
    checked=CheckedUpperContract(source,certificate)
    spec=dict(width=4,must=1,may=13,lower=2,upper=7,can_zero=True);instance=checked.refine(spec)
    reject('changed specialization lower bound',lambda:checked.verify_instance({**spec,'lower':6},instance))
    reject('changed specialization zero flag',lambda:checked.verify_instance({**spec,'can_zero':False},instance))
    bad=copy.deepcopy(instance);bad['answer']['maximum']=7
    reject('invented specialization maximum',lambda:checked.verify_instance(spec,bad))
    reject('incompatible runtime mask',lambda:checked.refine({**spec,'must':15,'may':1}))
    reject('Boolean width',lambda:checked.refine({**spec,'width':True}))
    sweep=(ROOT/'baseline/native/helper_14.inc').read_text().rstrip('\n')
    upper=(ROOT/'baseline/native/helper_13.inc').read_text().rstrip('\n')
    native=(ROOT/'baseline/native/helper_11.inc').read_text().rstrip('\n')
    mutated_native=source.replace(native,native.replace('return ','return 0 * ',1),1)
    reject('changed trusted native mask helper',lambda:produce(mutated_native))
    reverse=source.replace(sweep,sweep.replace('position--','position++'),1)
    reject('ascending source sweep',lambda:produce(reverse))
    mutant_sources=[
        ('strict_comparison',source.replace(sweep,sweep.replace('(value | bit) <= bound','(value | bit) < bound'),1)),
        ('reversed_comparison',source.replace(sweep,sweep.replace('(value | bit) <= bound','(value | bit) >= bound'),1)),
        ('wrong_sign_choice',source.replace(upper,upper.replace('upperBound < 0 || newUpperBound > upperBound','upperBound < 0 && newUpperBound > upperBound'),1)),
        ('zero_permission_reversed',source.replace(upper,upper.replace('!canBeZero','canBeZero'),1)),
        ('unproved_bound_return',source.replace(upper,upper.replace('return newUpperBound;','return upperBound;'),1))]
    for name,mutant in mutant_sources:
        if mutant==source:raise ValueError('Ineffective source mutation')
        reject('stale source certificate: '+name,lambda mutant=mutant:replay(mutant,certificate))
        result=produce(mutant)
        if result['status'] not in {'sweep_counterexample','order_counterexample'}:raise ValueError('Source mutant was proved: '+name)
        compiled=compile_source(mutant);witness=None
        for w in range(1,5):
            s=1<<(w-1)
            for must,may in masks(w):
                values=words(w,must,may)
                for bound in range(-s,s):
                    for zero in [False,True]:
                        case=dict(width=w,must=must,may=may,lower=-s,upper=bound,can_zero=zero)
                        result_word=execute_concrete(compiled,case);wanted=expected(case,values)
                        if result_word['maximum']!=wanted or (result_word['upper_query_status']=='empty')!=(wanted is None):
                            witness=dict(spec=case,exact_carrier=values,expected_maximum=wanted,mutated_execution=result_word);break
                    if witness:break
                if witness:break
            if witness:break
        if witness is None:raise ValueError('No concrete small-word witness for source mutant: '+name)
        record=dict(name=name,universal_attempt=result,concrete_witness=witness)
        (out/(name+'.java')).write_text(mutant)
        (out/(name+'.json')).write_text(json.dumps(record,indent=2)+'\n');mutants.append(record)
    rename_source=source
    for raw,names in [(upper,['bits','upperBound','mustBeSet','mayBeSet','canBeZero','newUpperBound']),
                      (sweep,['bits','bound','mustBeSet','mayBeSet','initialValue','optionalBits','value','position','bit'])]:
        mapping={name:'renamed_'+str(i) for i,name in enumerate(names)}
        renamed=re.sub(r'\b('+ '|'.join(names)+r')\b',lambda m:mapping[m.group()],raw)
        rename_source=rename_source.replace(raw,renamed,1)
    reversed_operands=source.replace(sweep,sweep.replace('(value | bit) <= bound','bound >= (bit | value)'),1)
    for name,variant in [('local_and_parameter_renaming',rename_source),('comparison_and_or_operand_order',reversed_operands)]:
        result=produce(variant)
        if result['status']!='certificate_produced':raise ValueError('Lost harmless source variant: '+name)
        verified=replay(variant,result['certificate']);variants.append(dict(name=name,status=verified['status'],sweep_states=verified['sweep']['states']))
        (out/(name+'.java')).write_text(variant)
        (out/(name+'_certificate.json')).write_text(json.dumps(result['certificate'],indent=2)+'\n')
    result=dict(status='passed',negative_checks=len(rejections),rejections=rejections,
                source_mutants=len(mutants),concrete_mutant_witnesses=len(mutants),source_variants=variants)
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rejections'}),flush=True);return result


if __name__=='__main__':run(ROOT/'validation/certificates_v1')
