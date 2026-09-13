"""Development checks independent of semantic-view construction and proof rows."""
import copy,itertools,json,random
from environment import ROOT,save
from semantic_view import view,source_view
from row_observation_producer import produce
from row_observation_kernel import verify
from semantic_choice_producer import produce as rewrite
from semantic_choice_kernel import replay
from word_oracle import expr_value
from representation_cases import cases,A,B,C,Z,ONE,T


def main():
    rng=random.Random(20260913);checks=0;records=[]
    # Numeric order, signed boundaries, Boolean polarity and min/max ties.
    probes=[('cmp'+str(p),A,B) for p in range(10)]
    probes += [(op,A,B) for op in ['umin','umax','smin','smax']]
    probes += [('select',('cmp'+str(p),A,B),A,B) for p in range(10)]
    probes += [('and',A,('and',('const',2),ONE)),('or',A,('or',('const',3),('const',-4)))]
    for e in probes:
        v=view(e);assert view(v)==v
        for w in range(2,6):
            for a,b in itertools.product(range(1<<w),repeat=2):
                assert expr_value(e,[a,b],w)==expr_value(v,[a,b],w),(e,v,w,a,b);checks+=1
    # Small representative development set. The complete declared suite runs
    # after freeze; no test cases are discarded based on success.
    selected=[];seen=set()
    for row in cases():
        if row['family'] in seen:continue
        seen.add(row['family']);selected.append(row)
    for row in selected:
        e,g=row['expression'],row['guards'];cert=produce(e,g);values,_=verify(e,g,json.loads(json.dumps(cert)))
        assert values==row['expected'],(row['family'],values,row['expected'])
        for w in [2,3,4]:
            for vals in itertools.product(range(1<<w),repeat=3):
                a=expr_value(e,list(vals),w);b=expr_value(view(e),list(vals),w);assert a==b;checks+=1
                if all(bool(expr_value(p,list(vals),w))==t for p,t in g):assert a in {x% (1<<w) for x in values},(row['family'],w,vals)
        for w in [8,16,64,257]:
            for _ in range(10):
                vals=[rng.randrange(1<<w) for _ in range(3)];assert expr_value(e,vals,w)==expr_value(view(e),vals,w);checks+=1
                if all(bool(expr_value(p,vals,w))==t for p,t in g):assert expr_value(e,vals,w) in {x% (1<<w) for x in values}
        records.append(dict(family=row['family'],source=e,guards=g,certificate=cert))
    e=('umin',ONE,A);c=produce(e,[]);corruptions=[]
    for what in ['schema','width','source','view','guards','missing_branch','false_cover','wrong_selector','wrong_row']:
        bad=copy.deepcopy(c)
        if what=='schema':bad['schema']='bad'
        elif what=='width':bad['minimum_width']=1
        elif what in ['source','view','guards']:bad[what+'_hash']='0'*64
        elif what=='missing_branch':del bad['proof']['false']
        elif what=='false_cover':bad['values']=[1]
        elif what=='wrong_selector':bad['proof']['selector']=('select',('cmp6',A,ONE),ONE,Z)
        else:bad['proof']['true']['rows'][0]['output']=7
        try:verify(e,[],bad)
        except (ValueError,KeyError,IndexError,TypeError):corruptions.append(what)
        else:raise AssertionError('corruption accepted '+what)
    # A shared finite range does not establish equality of the observed maps.
    other=('and',A,ONE);assert produce(other,[])['values']==c['values']
    try:verify(other,[],c)
    except ValueError:corruptions.append('same-range-different-source')
    else:raise AssertionError('range mistaken for word equality')
    assert expr_value(e,[2],2)!=expr_value(other,[2],2)
    # Empty-cell replacement must only occur under the contradictory source path.
    root=('select',('cmp6',A,Z),('mul',B,('umin',ONE,A)),Z)
    after,trace,stats=rewrite(root,'rows');replay(root,trace,after)
    for w in range(2,6):
        for a,b in itertools.product(range(1<<w),repeat=2):assert expr_value(root,[a,b],w)==expr_value(after,[a,b],w);checks+=1
    save(ROOT/'validation/development.json',dict(status='passed',concrete_comparisons=checks,development_families=len(selected),
       corruptions_rejected=corruptions,same_range_separation=dict(width=2,input=2,umin=1,mask=0),
       empty_cell_rewrite=dict(before=root,after=after,trace=trace)))
    save(ROOT/'validation/development_certificates.json',records)
    print('Passed',checks,'comparisons,',len(selected),'families,',len(corruptions),'corruption probes')


if __name__=='__main__':main()
