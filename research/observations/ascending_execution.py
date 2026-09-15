"""Whole-integer execution of the checked ascending region's original AST.

Kept separate from residual slice rules, search and native-Java validation so
counterexample replay does not import a producer, subprocess or a JVM harness.
This is the former ascending_validation interpreter, with unchanged operations.
"""
from .model import require


def expression(n, env):
    if n[0] in {'number', 'boolean'}: return n[1]
    if n[0] == 'name': return env[n[1]]
    if n[0] == 'unary':
        x = expression(n[2], env)
        return {'!': lambda: not x, '~': lambda: ~x, '-': lambda: -x, '+': lambda: x}[n[1]]()
    require(n[0] == 'binary', 'raw integer expression')
    a = expression(n[2], env); op = n[1]
    if op == '&&': return bool(a and expression(n[3], env))
    if op == '||': return bool(a or expression(n[3], env))
    b = expression(n[3], env)
    return {'+': lambda: a + b, '-': lambda: a - b, '&': lambda: a & b,
            '|': lambda: a | b, '^': lambda: a ^ b, '<<': lambda: a << b,
            '==': lambda: a == b, '!=': lambda: a != b,
            '<': lambda: a < b, '>': lambda: a > b, '<=': lambda: a <= b,
            '>=': lambda: a >= b}[op]()


def statement(s, env):
    kind = s[0]
    if kind == 'block':
        for x in s[1]: statement(x, env)
    elif kind == 'declare': env[s[2]] = expression(s[3], env)
    elif kind == 'if': statement(s[2] if expression(s[1], env) else s[3], env)
    elif kind == 'for':
        env[s[1]] = expression(s[2], env)
        while expression(s[3], env):
            statement(s[6], env); env[s[1]] += 1 if s[5] == '+' else -1
    else:
        value = expression(s[2], env); name = s[1]
        if kind == 'assign': env[name] = value
        elif kind == 'add_assign': env[name] += value
        elif kind == 'or_assign': env[name] |= value
        elif kind == 'and_assign': env[name] &= value
        elif kind == 'xor_assign': env[name] ^= value
        else: raise ValueError('raw integer statement')


def environment(region, width, must, may, seed):
    names = region['names']
    optional = next(name for name, alias in region['aliases'].items() if alias == 'optional')
    return {names[0]: width + 1, names[2]: must, names[3]: may,
            region['word']: seed, optional: may & ~must & ((1 << width) - 1)}


def integer_value(region, key):
    env = environment(region, *key)
    for decl in region['declarations']: statement(decl, env)
    statement(region['loop'], env)
    return env[region['word']] & ((1 << key[0]) - 1)
