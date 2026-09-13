"""Development checks: all finite input words, large widths and corruptions."""
import copy,itertools,json,random
from environment import ROOT,save
from qkf_certifier.kernel import digest
from regular_interfaces import order
from word_oracle import expr_value
from boundary_cases import cases
import boundary_kernel as K


def trace_for(e,engine):
    after,proof=K.derive(e,[],engine)
    t=dict(schema=K.SCHEMA,minimum_width=2,path=[],engine=engine,guards=[],before_hash=digest(e),
        after_hash=digest(after),after=after,proof=proof)
    K.replay(e,[t],after);return after,t


def assignments(e,w,rng=None,samples=0):
    indices=sorted({n[1] for n in order(e) if n[0]=='var'})
    source=itertools.product(range(1<<w),repeat=len(indices)) if rng is None else (
        tuple(rng.randrange(1<<w) for _ in indices) for _ in range(samples))
    for vals in source:
        row=[0]*4
        for i,v in zip(indices,vals):row[i]=v
        yield row


if __name__=='__main__':
    rs=cases();families={}
    for r in rs:families.setdefault(r['family'],r)
    checks=0;accepted=[];rejected=[];rng=random.Random(9132026)
    for r in families.values():
        e=r['expression'];engine='endpoints' if r['role']=='endpoints' else 'position'
        try:out,t=trace_for(e,engine)
        except ValueError as ex:
            assert r['role']=='unsupported-relocation',(r['id'],str(ex));rejected.append(dict(id=r['id'],reason=str(ex)));continue
        assert r['role']!='unsupported-relocation'
        for w in [2,3,4]:
            for vals in assignments(e,w):
                assert expr_value(e,vals,w)==expr_value(out,vals,w),(r['id'],w,vals);checks+=1
        for w in [8,16,64,257]:
            for vals in assignments(e,w,rng,32):
                assert expr_value(e,vals,w)==expr_value(out,vals,w),(r['id'],w,vals);checks+=1
        accepted.append(dict(id=r['id'],source=e,after=out,trace=t))
    endpoint=next(r for r in accepted if r['trace']['engine']=='endpoints')
    position=next(r for r in accepted if r['trace']['engine']=='position')
    corruptions=[]
    def corrupt(name,record,mutate):
        t=copy.deepcopy(record['trace']);mutate(t)
        try:K.replay(record['source'],[t],record['after'])
        except (ValueError,KeyError,IndexError,TypeError):corruptions.append(name);return
        raise AssertionError('accepted corruption: '+name)
    corrupt('schema',endpoint,lambda t:t.update(schema='wrong'))
    corrupt('minimum-width',endpoint,lambda t:t.update(minimum_width=1))
    corrupt('source',endpoint,lambda t:t.update(before_hash='wrong'))
    corrupt('guards',endpoint,lambda t:t.update(guards=[(('true',),False)]))
    corrupt('engine',endpoint,lambda t:t.update(engine='position'))
    corrupt('missing-cell',endpoint,lambda t:t['proof']['derivation']['cells'].pop())
    corrupt('exception-width',endpoint,lambda t:t['proof']['derivation']['cells'][0]['phases'][0].update(width=3))
    corrupt('affine-bound',endpoint,lambda t:t['proof']['derivation']['cells'][0]['phases'][1]['scalar_steps'][0].update(interval=[[0,0,9],[0,0,9]]))
    corrupt('protected-bits',position,lambda t:t['proof']['derivation']['observation'].update(protected_bits=[0,0]))
    corrupt('prefix-cell',position,lambda t:t['proof']['derivation']['observation']['supplied_cells'][0].update(prefix=1))
    corrupt('prefix-end',position,lambda t:t['proof']['derivation'].update(target_side='wrong'))
    corrupt('result',position,lambda t:t.update(after=('zero',)))
    # Both counts are proper, while the required effects differ.
    w=4;ys=[8,12];n=[expr_value(('countl_one',('var',0)),[y],w) for y in ys]
    shifts=[13>>k for k in n];masks=[15&~((1<<(w-1-k))-1) for k in n]
    assert n==[1,2] and shifts==[6,3] and masks==[12,14]
    separation=dict(width=w,run_words=ys,counts=n,endpoint_labels=['proper','proper'],shift_data=13,shift_outputs=shifts,mask_data=15,mask_outputs=masks)
    # General action separation: all-ones distinguishes every n=0..w.
    lower_bound_checks=[]
    for w in [2,3,4,8,16,64,257]:
        ys=[((1<<w)-1)>>n for n in range(w+1)]
        assert len(set(ys))==w+1
        lower_bound_checks.append(dict(width=w,distinct_action_outputs=len(set(ys))))
    save(ROOT/'validation/development.json',dict(status='passed',comparisons=checks,families=len(families),
        accepted=len(accepted),retained_unresolved=len(rejected),corruptions_rejected=corruptions,
        insufficient_endpoint_factor=separation,action_separation_samples=lower_bound_checks))
    save(ROOT/'validation/development_certificates.json',dict(accepted=accepted,rejected=rejected))
    print('Passed',checks,'comparisons;',len(accepted),'families supported;',len(rejected),'retained refusals;',len(corruptions),'corruptions rejected')
