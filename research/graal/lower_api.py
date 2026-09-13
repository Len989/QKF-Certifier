"""Concrete source execution and a checked, scoped lower-bound refinement API."""
import json
from pathlib import Path
from carry_kernel import require,digest
from lower_kernel import replay
from universal_api import CheckedUpperContract,validate,signed
ROOT=Path(__file__).resolve().parent

def sign_admissible(s):return s['lower']<=0 or not(s['may'] & (1<<(s['width']-1)))
def member(s,v):
    w=s['width'];sign=1<<(w-1);u=v&((1<<w)-1)
    return -sign<=v<sign and (u&s['must'])==s['must'] and not(u&~s['may']) and (s['can_zero'] or v!=0)

def execute_concrete(s,program=None,guard=None):
    """Exact Java long operations for w<=64; explicitly defined wider semantic lift.
    The native empty branch ctz(0)=64 and shift-distance masking are retained.
    This interpreter is checked independently against the original Java bodies.
    """
    validate(s);w=s['width'];host=max(64,w);mod=1<<host;hs=mod>>1
    def wrap(v):return (v+hs)%mod-hs
    m,a,L=s['must'],s['may'],s['lower'];bit_sign=1<<(w-1)
    value=signed(m|bit_sign if a&bit_sign else m,w);optional=a&~m&(bit_sign-1);path=['minimum']
    first_comparison=[-1,0] if guard is None else guard[2][1]
    program=program or dict(mandatory_action='or',forbidden_action='add',first_action='add')
    if value<L:
        if optional==0:value=0;path.append('no_optional_zero')
        else:
            for i in range(w-1,-1,-1):
                bit=1<<i
                if optional&bit and ((wrap(value+bit)>L)-(wrap(value+bit)<L)) in first_comparison:value=wrap(value+bit)
            require(value<=L,'source GraalError guarantee');path.append('greedy')
            if value<L:
                incremented=False
                for i in range(w-1):
                    bit=1<<i
                    if incremented:
                        if bit&m and not(value&bit):
                            value=wrap(value|bit) if program['mandatory_action']=='or' else wrap(value+bit)
                        if not(bit&a) and value&bit:
                            value=wrap(value+bit) if program['forbidden_action']=='add' else wrap(value|bit)
                    elif bit&optional:
                        value=wrap(value+bit) if program['first_action']=='add' else wrap(value|bit);incremented=True
                path.append('successor')
    if value==0 and not s['can_zero']:
        hm=wrap(m)
        if hm>0:value=hm
        elif hm==0:
            lowbit=(a&-a).bit_length()-1 if a else host
            value=wrap(1<<(lowbit%host))
        else:value=bit_sign-1
        path.append('exclude_zero')
    if value<L:value=bit_sign-1;path.append('maximum_sentinel')
    return dict(source_long_result=value,source_path=path)

class CheckedLowerContract:
    def __init__(self,source,certificate):
        self.proof=replay(source,certificate);self.compiled=certificate['compiled_source']
        # Exact emptiness is an independently checked use of the preceding upper theorem.
        upper_source=(ROOT/'previous/baseline/source/IntegerStamp.java').read_text()
        require(source==upper_source,'this combined API is bound to the original complete source; renamed lower variants are proof-only diagnostics')
        upper_certificate=json.loads((ROOT/'previous/results/main/universal_upper/certificate.json').read_text())
        self.upper=CheckedUpperContract(upper_source,upper_certificate)

    def refine(self,s):
        validate(s)
        if not sign_admissible(s):
            return dict(status='unsupported_source_sign_context',spec=dict(s),binding=digest(s),reason='positive lower bound with a may-mask that still allows negative words; caller preparation must be proved before this helper contract can be used')
        answer=execute_concrete(s,self.compiled['carry_program'],self.compiled['sweep_guard']);v=answer['source_long_result']
        upper=self.upper.refine(s);empty=upper['joint_empty'];exact=not empty and member(s,v) and v<=s['upper']
        require(v>=s['lower'],'native final guard')
        return dict(status='proved_lower_refinement',spec=dict(s),binding=digest(s),universal_certificate_sha256=self.proof['certificate_sha256'],
                    upper_dependency_sha256=upper['universal_certificate_sha256'],answer=answer,joint_empty=empty,
                    precision='empty' if empty else 'exact_minimum' if exact else 'conservative_bound',
                    minimum=v if exact else None,refined_spec={**s,'lower':v},
                    guarantee='same complete joint mask/range/nonzero carrier; emptiness uses the preceding upper theorem, not the numeric MAX sentinel')

    def verify_instance(self,s,record):
        require(record==self.refine(s),'complete lower specialization and source binding')
        return dict(status='verified_lower_specialization',refinement_status=record['status'])
