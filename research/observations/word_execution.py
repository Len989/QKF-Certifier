"""Direct integer execution of the restricted source IR, without proof search."""


def integer_guard(guard, optional, trial, right, tests):
    tag = guard[0]
    if tag == 'optional': return optional
    if tag == 'test':
        t = tests[guard[1]]; bound = right + t['offset']; op = t['op']
        return {'<': trial < bound, '<=': trial <= bound, '==': trial == bound,
                '!=': trial != bound, '>': trial > bound, '>=': trial >= bound}[op]
    if tag == 'not': return not integer_guard(guard[1], optional, trial, right, tests)
    a = integer_guard(guard[1], optional, trial, right, tests)
    b = integer_guard(guard[2], optional, trial, right, tests)
    return a and b if tag == 'and' else a or b


def integer_execute(ir, key):
    width, bound, must, may, initial = key
    optional = may & ~must & ((1 << width) - 1)
    value = initial; right = key[int(ir['comparison_word'][-1])]
    for position in reversed(range(width)):
        bit = 1 << position
        if integer_guard(ir['guard'], bool(optional & bit), value | bit, right, ir['tests']): value |= bit
    return value
