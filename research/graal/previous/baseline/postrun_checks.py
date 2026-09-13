"""Additional diagnostics after freeze; no changes to the tested algorithm."""
import copy,json
from pathlib import Path
from native_java import evaluate
from joint_producer import produce
from joint_kernel import replay
from validate_source_bridge import stamp,included
ROOT=Path(__file__).resolve().parent


def run():
    out=ROOT/'postrun';out.mkdir(exist_ok=False);records=[]
    for w in [4,8,32,64]:
        s=1<<(w-1);original=dict(width=w,must=0,may=s|1,lower=-s+1,upper=1,can_zero=False)
        line=evaluate([f'create {w} {-s+1} 1 0 {s|1:x} 0'])[0];returned=stamp(line,w)
        q={'kind':'summary'};certificate=produce(returned,q);summary=replay(returned,q,certificate)['answer']
        assert returned['must']==0 and returned['may']==s|1
        assert summary['count']==2 and summary['must']==1 and summary['may']==s|1
        strengthened={**returned,'must':1};strong_certificate=produce(strengthened,q);strong=replay(strengthened,q,strong_certificate)['answer']
        assert included(summary,strengthened) and included(strong,returned)
        counterexamples=[]
        for name,weakened in [('allow_zero',{**returned,'can_zero':True}),('remove_interval',{**returned,'lower':-s,'upper':s-1}),('remove_mask',{**returned,'must':0,'may':(1<<w)-1})]:
            bit={'kind':'bit','index':0};proof=produce(weakened,bit);a=replay(weakened,bit,proof)['answer'];assert a['support']==3
            counterexamples.append(dict(removed=name,spec=weakened,certificate=proof,separating_word=a['witnesses']['0']))
        data=dict(width=w,native_supported=w in [1,8,16,32,64],input_spec=original,java_output=line,returned_spec=returned,
                  joint_certificate=certificate,strengthened_spec=strengthened,strengthened_certificate=strong_certificate,
                  extra_explicit_known_one_bits=1,same_concrete_carrier=True,counterexamples=counterexamples,
                  interpretation='The complete Graal stamp already implies this bit. The joint query exposes it and permits a mask update without shrinking its represented word set.')
        (out/f'implicit_bit_{w}.json').write_text(json.dumps(data,indent=2)+'\n')
        records.append(dict(width=w,represented_words=2,original_must=0,derived_must=1,cover_cells=len(certificate['cells']),negative_contexts=3))
    # Check the new serialization/replay layer for the finite paper example.
    from theory_certificate import replay as theory_replay
    proof=json.loads((ROOT/'theory/certificate.json').read_text());negative=[]
    mutations=[('missing derivation',lambda x:x['positive_events'].clear()),
               ('collapsed lower separator',lambda x:x['lower_model']['constants'].__setitem__('A::one',x['lower_model']['operations']['alpha'][-1][1])),
               ('changed ground equation',lambda x:x['equations'].pop()),
               ('false row kernel',lambda x:x['row_kernel'].append(['both']))]
    for name,change in mutations:
        bad=copy.deepcopy(proof);change(bad)
        try:theory_replay(bad)
        except (AssertionError,ValueError,KeyError,IndexError):negative.append(name)
        else:raise AssertionError('accepted false theory evidence: '+name)
    result=dict(status='passed',implicit_bit_examples=records,theory_mutations_rejected=negative,
                timing='After the frozen main run; diagnostic examples are not added to the five-program denominator.')
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':run()
