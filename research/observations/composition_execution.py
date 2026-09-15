"""Direct region execution and independent source-factor controls for composition.

The JSON wrapper is interpreted, not imported/executed as host code. Its calls
run the existing full-integer IR/AST semantics. check_factor controls the emitted
word against checked source factors, without requiring the strong goal lemmas.
An out-of-contract call is not a refutation of the requested composition target.
"""
from .ascending_execution import integer_value
from .ascending_kernel import Runner as AscendingRunner
from .ascending_source import extract_region
from .composition_program import execute
from .composition_spec import ROLES, validate_input
from .model import require
from .source_factor import Runner as DescendingRunner
from .word_execution import integer_execute


class CallDomainError(ValueError):
    pass


class Execution:
    def __init__(self, sources, source_certificates):
        require(type(sources) is dict and set(sources) == set(ROLES), 'two external region sources')
        require(type(source_certificates) is dict and set(source_certificates) == set(ROLES),
                'two checked region models')
        self.ascending = AscendingRunner(sources['ascending'], source_certificates['ascending'])
        self.descending = DescendingRunner(sources['descending'], source_certificates['descending'])
        self.ir = source_certificates['descending']['word']['source_ir']
        self.region = extract_region(sources['ascending'])

    def invoke(self, role, width, args, *, check_factor=True):
        m, a, g = (args[k] for k in ('must', 'may', 'seed'))
        optional = a & ~m & ((1 << width) - 1)
        if role == 'ascending':
            if g & m != m or g & ~a:
                raise CallDomainError('ascending call outside legal masked entry')
            y = integer_value(self.region, (width, m, a, g))
            if check_factor:
                word = [''.join(str((x >> i) & 1) for x in (m, a, g)) for i in range(width)]
                bits = self.ascending.run(word)['outputs']
                require(y == sum(int(x) << i for i, x in enumerate(bits)), 'composed ascending source/factor agreement')
            return y
        if g & optional:
            raise CallDomainError('descending call outside disjoint seed entry')
        b = args['bound']
        y = integer_execute(self.ir, (width, b, m, a, g))
        if check_factor:
            right = (b, m, a, g)[int(self.ir['comparison_word'][-1]) - 1]
            word = [''.join(str((x >> i) & 1) for x in (g, optional, right, y)) for i in range(width)]
            answer = self.descending.run(word)
            require(answer['accepted'], 'composed descending source/factor agreement')
        return y

    def run(self, program, inputs, *, check_factor=True):
        validate_input(inputs)
        return execute(program, inputs, lambda role, width, args:
                       self.invoke(role, width, args, check_factor=check_factor))
