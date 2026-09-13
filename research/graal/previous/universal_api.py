"""Instantiate the proved upper contract; distinguish a sentinel from a true minimum."""
from row_kernel import require,select,compare,digest
from order_kernel import execute
from universal_kernel import replay


def signed(x,width):
    return x-(1<<width) if x & (1<<(width-1)) else x


def validate(spec):
    require(set(spec)=={'width','must','may','lower','upper','can_zero'},'joint input fields')
    w=spec['width'];require(type(w) is int and 1<=w<=4096,'runtime width budget')
    require(all(type(spec[n]) is int for n in ['must','may','lower','upper']),'integer input')
    s=1<<(w-1);mask=(1<<w)-1
    require(0<=spec['must']<=mask and 0<=spec['may']<=mask and not(spec['must']&~spec['may']),'compatible masks')
    require(-s<=spec['lower']<s and -s<=spec['upper']<s and type(spec['can_zero']) is bool,'typed range/zero flag')


def execute_concrete(compiled,spec):
    """Numeric interpreter of the same compiled IR, also used for mutant diagnostics."""
    validate(spec);w=spec['width'];s=1<<(w-1);m,y,u=spec['must'],spec['may'],spec['upper']
    minimum=signed(m|s if y&s else m,w)
    ranks=dict(zero=0,must=signed(m,w),minimum=minimum,negative_maximum=signed(y,w) if y&s else 0,bound=u)
    guard=compiled['sweep']['guard'];optional=y&~m&(s-1)
    def sweep(initial):
        value=initial
        for position in range(w-1,-1,-1):
            bit=1<<position
            if select(guard,bool(optional&bit),compare(value|bit,u)):value|=bit
        return value
    result,initial,path=execute(compiled['upper']['ir'],ranks,bool(y&s),spec['can_zero'],sweep_value=sweep)
    mode,value,_=result
    return dict(upper_query_status=mode,source_long_result=-s if mode=='empty' else value,
                maximum=None if mode=='empty' else value,source_path=path,initial_value=initial)


class CheckedUpperContract:
    def __init__(self,source,certificate):
        self.proof=replay(source,certificate);self.compiled=certificate['compiled_source']

    def refine(self,spec):
        answer=execute_concrete(self.compiled,spec)
        empty=answer['upper_query_status']=='empty' or spec['lower']>answer['maximum']
        refined={**spec,'upper':answer['source_long_result']}
        return dict(status='proved_upper_refinement',spec=dict(spec),binding=digest(spec),
                    universal_certificate_sha256=self.proof['certificate_sha256'],answer=answer,
                    joint_empty=empty,refined_spec=refined,
                    guarantee='same complete joint word carrier; maximum is the exact upper observation when the joint carrier is nonempty')

    def verify_instance(self,spec,instance):
        require(instance==self.refine(spec),'universal specialization binding and source execution')
        return dict(status='verified_upper_refinement',joint_empty=instance['joint_empty'])
