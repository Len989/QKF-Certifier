"""Finite instances illustrating the exact opposite-end observer lower bound."""
import argparse
from pathlib import Path
from common import ROOT,setup,save
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,required=True);a=ap.parse_args();setup(a.repo)
    from word_oracle import operation
    rows=[]
    for i in range(1,33):
        for j in range(1,33):
            w=i+j;x=((1<<j)-1)<<i;y=(1<<i)-1
            count=operation('countl_one',[x],None,w)
            output=operation('set_low_bits',[0,count],None,w)
            accepted=output==y
            assert accepted==(i==j)
            rows.append({'a_prefix_length':i,'b_suffix_length':j,'width':w,'input_word':x,'proposed_output':y,'actual_output':output,'accepted':accepted})
    save(ROOT/'results/opposite_end_boundary.json',{'status':'passed','instances':len(rows),'N':32,'maximum_width':64,'rows':rows,
        'meaning':'Illustrates, but does not replace, the proof in PROOFS.md: an exact synchronized NFA needs at least N states to recognize these N prefix/suffix pairs. No fixed finite NFA works for all widths.',
        'scope_limit':'A lower bound on exact full-function bit relations, not on every property-specific semantic quotient or on other symbolic reasoning models.'})
    print('Opposite-end fooling-set instances checked:',len(rows))
if __name__=='__main__':main()
