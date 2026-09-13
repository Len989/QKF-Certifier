"""Propose scoped order derivations for the generic mask-hull source lemma."""
import json
from mask_terms import tree,bit,rows,sign_rows,valid_table,lo,hi,ZERO
from hull_kernel import SCHEMA,native_bindings,prefix_rows,optional_rows,NATIVE_STEPS,check_le


def plain(v):return json.loads(json.dumps(v))


def bound(a,b,guards):
    a,b=tree(a),tree(b);premises=[];table=[]
    if a==b:rule='reflexive'
    elif b[0]=='min':rule='minimum_right';premises=[bound(a,b[1],guards),bound(a,b[2],guards)]
    elif a[0]=='lo' and b==hi(a[1]):rule='cube_minimum_maximum';table=valid_table(a[1])
    elif a==ZERO and b[0]=='lo':
        rule='zero_below_cube';table=[[list(r),bit(b[1][2],r)] for r in sign_rows(guards)]
    elif a[0]=='hi' and b[0]=='hi':
        rule='maximum_subset';table=dict(non_sign=[[list(r),bit(a[1][2],r),bit(b[1][2],r)] for r in rows()],
                                         sign=[[list(r),bit(a[1][1],r),bit(b[1][1],r)] for r in sign_rows(guards)])
    else:raise ValueError('No supported observation proves this interval redundant')
    proof=dict(rule=rule,left=plain(a),right=plain(b),premises=premises,rows=table)
    check_le(a,b,guards,proof);return proof


def produce_hull(source,cube,lower,upper,can_zero,guards):
    if can_zero is not True:raise ValueError('can_zero premise absent')
    return dict(schema=SCHEMA,cube=plain(cube),lower=plain(lower),upper=plain(upper),can_zero=True,guards=plain(guards),
                bindings=native_bindings(source),mask_rows=valid_table(cube),
                lower_proof=bound(lower,lo(cube),guards),upper_proof=bound(hi(cube),upper,guards),
                prefix_rows=prefix_rows(),optional_rows=optional_rows(),native_steps=NATIVE_STEPS,
                conclusion=dict(must=plain(cube[1]),may=plain(cube[2]),carrier='unchanged',bounds='attained signed mask extrema',
                                maximum_passes=2,mathematical_widths='all positive',java_widths=[1,8,16,32,64],
                                trust='Reviewed native loop/ordering bridge plus exact helper-body binding; not a formal Java compiler proof.'))
