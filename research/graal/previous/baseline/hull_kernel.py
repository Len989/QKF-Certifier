"""Reviewed native bridge for an interval redundant on a protected mask carrier.

The finite rows prove bitwise premises and a two-state prefix invariant for
all word lengths. The source-bound loop lemma is explicitly part of the
trusted native semantics, not a claim of a machine formalization of Java.
"""
import hashlib,json,re
from pathlib import Path
from mask_terms import tree,bit,rows,sign_rows,valid_table,lo,hi,ZERO
from native_java import block_end

ROOT=Path(__file__).resolve().parent
SCHEMA='qkf-source-mask-hull-native-lemma-v1'


def require(p,m):
    if not p:raise ValueError(m)


def native_bindings(source):
    """Allow a changed outer procedure only when every native helper is intact."""
    manifest=json.loads((ROOT/'native/MANIFEST.json').read_text());out={}
    for record in manifest['extracted']:
        if not record['name'].startswith('helper_'):continue
        original=(ROOT/'native'/(record['name']+'.inc')).read_text().rstrip('\n')
        declaration=original[:original.index('{')]
        start=source.find(declaration);require(start>=0,'native declaration missing: '+record['name'])
        end=block_end(source,source.index('{',start));actual=source[start:end]
        h=hashlib.sha256(actual.encode()).hexdigest()
        require(h==record['sha256'],'changed native body: '+record['name']);out[record['name']]=h
    limits=re.findall(r'\bITERATION_LIMIT\s*=\s*(\d+)\s*;',source)
    require(limits==['3'],'source iteration limit')
    return dict(helper_hashes=out,iteration_limit=3,
                dependency_semantics='The documented CodeUtil/uncached-factory shims of the previous frozen Graal transcription.')


def check_le(a,b,guards,proof):
    a,b=tree(a),tree(b);guards=tree(guards)
    require(isinstance(proof,dict) and proof.get('left')==json.loads(json.dumps(a)) and proof.get('right')==json.loads(json.dumps(b)),'bound proposition binding')
    rule=proof.get('rule');premises=proof.get('premises')
    require(set(proof)=={'rule','left','right','premises','rows'},'bound proof fields')
    if rule=='reflexive':require(a==b and premises==[] and proof['rows']==[],'reflexive bound');return
    if rule=='minimum_right':
        require(b[0]=='min' and len(premises)==2 and proof['rows']==[],'minimum premises')
        check_le(a,b[1],guards,premises[0]);check_le(a,b[2],guards,premises[1]);return
    if rule=='cube_minimum_maximum':
        require(a[0]=='lo' and b==hi(a[1]) and premises==[],'cube endpoints')
        require(proof['rows']==valid_table(a[1]),'endpoint carrier');return
    if rule=='zero_below_cube':
        require(a==ZERO and b[0]=='lo' and premises==[],'nonnegative cube proposition')
        valid_table(b[1]);table=[[list(r),bit(b[1][2],r)] for r in sign_rows(guards)]
        require(all(v==0 for _,v in table) and proof['rows']==table,'cube sign was not forced');return
    if rule=='maximum_subset':
        require(a[0]=='hi' and b[0]=='hi' and premises==[],'maximum subset proposition')
        ca,cb=a[1],b[1];valid_table(ca);valid_table(cb)
        lower=[[list(r),bit(ca[2],r),bit(cb[2],r)] for r in rows()]
        signs=[[list(r),bit(ca[1],r),bit(cb[1],r)] for r in sign_rows(guards)]
        # All non-sign bits are a subset; signed order places sign=1 before 0.
        require(all(x<=y for _,x,y in lower),'lower-bit subset not forced')
        require(all(x>=y for _,x,y in signs),'signed endpoint order not forced')
        require(proof['rows']==dict(non_sign=lower,sign=signs),'endpoint order cells');return
    raise ValueError('unsupported bound inference: '+repr(rule))


def prefix_rows():
    table=[]
    for is_sign in [True,False]:
        for same in ([True] if is_sign else [False,True]):
            for m,y in [(0,0),(0,1),(1,1)]:
                a,b=(y,m) if is_sign else (m,y)
                equal=same and a==b;bm,by=(a,a) if equal else (0,1)
                require((m|bm,y&by)==(m,y),'prefix mask preservation')
                table.append(dict(sign=is_sign,prefix_equal=same,must=m,may=y,low=a,high=b,
                                  next_equal=equal,bounded_must=bm,bounded_may=by))
    return table


def optional_rows():
    out=[]
    for m,y in [(0,0),(0,1),(1,1)]:
        for current in range(m,y+1):
            optional=y and not m;after=1 if optional else current
            require(after==y,'optional-bit endpoint')
            out.append(dict(must=m,may=y,current=current,optional=bool(optional),after=after))
    return out


NATIVE_STEPS=[
 'compatible_mask_has_attained_signed_extrema',
 'enclosing_interval_cannot_trigger_input_empty',
 'unrestricted_mask_forces_full_interval_in_factory_shortcut',
 'first_clamp_is_exact_mask_hull',
 'equal_endpoints_take_constant_branch_before_java_shift_64',
 'common_prefix_adds_no_bit_constraint_on_mask_hull',
 'upper_endpoint_has_correct_fixed_sign',
 'every_optional_bit_fits_below_attained_upper_endpoint',
 'descending_pass_sets_all_optional_bits_and_preserves_sign',
 'lower_endpoint_equals_initial_value_so_both_lower_loops_are_skipped',
 'zero_exclusion_branch_disabled_by_real_can_zero_true',
 'empty_checks_false_for_compatible_hull',
 'first_update_is_monotone_and_second_pass_is_stable',
 'two_passes_fit_recorded_source_limit_three',
 'constructor_zero_flag_preserves_exact_word_carrier'
]


def replay_hull(source,cube,lower,upper,can_zero,guards,certificate):
    c=certificate;cube,lower,upper,guards=tree(cube),tree(lower),tree(upper),tree(guards)
    require(isinstance(c,dict) and set(c)=={'schema','cube','lower','upper','can_zero','guards','bindings','mask_rows','lower_proof','upper_proof','prefix_rows','optional_rows','native_steps','conclusion'},'hull certificate fields')
    require(c['schema']==SCHEMA and tree(c['cube'])==cube and tree(c['lower'])==lower and tree(c['upper'])==upper and tree(c['guards'])==guards,'hull source argument binding')
    require(can_zero is True and c['can_zero'] is True,'hull identity needs permission for zero')
    require(c['bindings']==native_bindings(source),'native source binding')
    require(c['mask_rows']==valid_table(cube),'complete compatible carrier cells')
    check_le(lower,lo(cube),guards,c['lower_proof']);check_le(hi(cube),upper,guards,c['upper_proof'])
    require(c['prefix_rows']==prefix_rows() and c['optional_rows']==optional_rows(),'all-width native induction rows')
    require(c['native_steps']==NATIVE_STEPS,'complete reviewed source derivation')
    expected=dict(must=json.loads(json.dumps(cube[1])),may=json.loads(json.dumps(cube[2])),
                  carrier='unchanged',bounds='attained signed mask extrema',maximum_passes=2,
                  mathematical_widths='all positive',java_widths=[1,8,16,32,64],
                  trust='Reviewed native loop/ordering bridge plus exact helper-body binding; not a formal Java compiler proof.')
    require(c['conclusion']==expected,'hull conclusion')
    return expected
