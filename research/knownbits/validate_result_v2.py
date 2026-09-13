"""Regression: an action can normalize into a different node kind."""
import argparse,json
from environment import ROOT,save
from qkf_certifier.kernel import Z,W
from corpus_io import load
import result_kernel as K
import result_v2_producer as P
import result_producer as FIRST


def run(out):
    bundle,_,_=load('KnownBits_AvgCeilU')
    authority=K.source_authority(bundle,'partial_solution_0')
    one=('const',1);a=('var',0)
    bit=('shl',one,('sub',W,one))
    terms=[bit,('shl',('add',one,Z),('sub',W,one)),
           ('shl',one,('sub',('add',W,Z),one)),
           ('shl',one,('sub',W,('clear_sign_bit',one))),
           ('lshr',a,('sub',('clear_sign_bit',one),one)),
           ('clear_low_bits',a,('sub',('clear_sign_bit',one),one))]
    records=[]
    for i,t in enumerate(terms):
        source=('pair',Z,t)
        final,trace,stats=P.produce(source,'observed',authority)
        checked,_=K.replay(source,trace,final,authority)
        assert checked==final
        records.append(dict(case=i,source=source,view=K.native(t),final=final,trace=trace,stats=stats))
    # The first term is the exact generic shape responsible for the frozen-v1
    # crash; a native sign-bit word has two fields and no shift-amount field.
    assert K.native(bit)==K.S and len(K.native(bit))==2
    try:FIRST.produce(('pair',Z,bit),'observed',authority)
    except IndexError:original_crash_reproduced=True
    else:raise AssertionError('the regression must reproduce the original crash')
    result=dict(status='passed',cases=len(records),records=records,
                original_crash_reproduced=original_crash_reproduced,
                limitation='robust proposal generation only; unchanged all-width kernel')
    save(out/'results.json',result);return dict(status='passed',cases=len(records))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
    out=ROOT/a.output;out.mkdir(parents=True,exist_ok=False);print(json.dumps(run(out)))
