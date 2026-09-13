"""Pull back partial bit rows through piecewise signed coordinate views.

No proof search. All intervals are finite lists of affine lower/upper bounds;
their actual start is the maximum lower bound. Constants either discharge a
row or yield a source-derived empty-intersection obligation.
"""
import sys


def action(word, _depth=0):
    """Return base word, position reversal, value flip for a bijective action."""
    if _depth > 16 or not isinstance(word, tuple) or not word:
        return None
    if word[0] == 'input' and len(word) == 2:
        return word[1], False, False
    if word[0] in {'not', 'reverse'} and len(word) == 2:
        inner = action(word[1], _depth+1)
        if inner is not None:
            name, reverse, flip = inner
            return name, reverse ^ (word[0] == 'reverse'), flip ^ (word[0] == 'not')
    return None


def transported_kind(kind, reverse, flip):
    leading = kind.startswith('cl') ^ reverse
    one = kind.endswith('o') ^ flip
    return ('cl' if leading else 'ct') + ('o' if one else 'z')


def affine(expr, compiler):
    K = sys.modules[type(compiler).__module__]
    if type(expr) is int: return K.const(expr)
    if isinstance(expr, str) and (expr == 'w' or expr in compiler.parameters): return K.var(expr)
    if isinstance(expr, tuple) and len(expr) == 3 and expr[0] in {'add', 'sub'}:
        return (K.add if expr[0] == 'add' else K.sub)(affine(expr[1], compiler), affine(expr[2], compiler))
    raise K.Unsupported('counted-view cuts require affine scalars without counts')


def regions(K, kind, number):
    zero, one, width = K.const(0), K.const(1), K.W
    leading = kind.startswith('cl')
    bit = int(kind.endswith('o'))
    start = K.sub(width, number) if leading else zero
    end = width if leading else number
    boundary = K.sub(K.sub(width, number), one) if leading else number
    return [dict(lower=[zero, start], upper=[width, end], guard=True, bit=bit),
            dict(lower=[zero, boundary], upper=[width, K.add(boundary, one)],
                 guard=K.lt(number, width), bit=1-bit)]


def pullback(compiler, kind, word, number):
    K = sys.modules[type(compiler).__module__]
    rows, constraints = [], []
    steps = [0]
    zero = K.const(0)
    def nonempty(row):
        return K.And(row['guard'], *(K.lt(lo, hi) for lo in row['lower'] for hi in row['upper']))
    def constant(row, bit):
        if row['bit'] != bit:
            constraints.append(K.Not(nonempty(row)))
    def part(row, lower=(), upper=(), guard=True, bit=None):
        return dict(lower=row['lower']+list(lower), upper=row['upper']+list(upper),
                    guard=K.And(row['guard'], guard), bit=row['bit'] if bit is None else bit)
    def shifted(row, amount):
        return dict(row, lower=[K.add(v, amount) for v in row['lower']],
                    upper=[K.add(v, amount) for v in row['upper']])
    def visit(expr, row, depth=0):
        steps[0] += 1
        if depth > 16 or steps[0] > 1024 or len(rows)+len(constraints) > 256:
            raise K.Unsupported('count-row transport construction budget')
        if not isinstance(expr, tuple) or not expr:
            raise K.Unsupported('counted-view syntax')
        op = expr[0]
        if op == 'input' and len(expr) == 2 and expr[1] in compiler.inputs:
            rows.append(dict(row, word=expr[1]))
        elif op in {'zero', 'ones'} and len(expr) == 1:
            constant(row, int(op == 'ones'))
        elif op == 'not' and len(expr) == 2:
            visit(expr[1], dict(row, bit=1-row['bit']), depth+1)
        elif op == 'reverse' and len(expr) == 2:
            transformed = dict(row, lower=[K.sub(K.W, hi) for hi in row['upper']],
                               upper=[K.sub(K.W, lo) for lo in row['lower']])
            visit(expr[1], transformed, depth+1)
        elif op in {'shl', 'lshr'} and len(expr) == 3:
            amount = affine(expr[2], compiler)
            valid = K.And(K.le(zero, amount), K.lt(amount, K.W))
            constant(part(row, guard=K.Not(valid)), 0)
            if op == 'shl':
                constant(part(row, upper=[amount], guard=valid), 0)
                transported = shifted(part(row, lower=[amount], guard=valid), K.scale(amount, -1))
            else:
                cut = K.sub(K.W, amount)
                constant(part(row, lower=[cut], guard=valid), 0)
                transported = shifted(part(row, upper=[cut], guard=valid), amount)
            visit(expr[1], transported, depth+1)
        elif op in {'and', 'or', 'xor'} and len(expr) == 3:
            if isinstance(expr[2], tuple) and expr[2][0] in {'lowmask', 'highmask'}:
                inner, mask = expr[1], expr[2]
            elif isinstance(expr[1], tuple) and expr[1][0] in {'lowmask', 'highmask'}:
                inner, mask = expr[2], expr[1]
            else:
                raise K.Unsupported('counted binary view requires one interval mask')
            if len(mask) != 2: raise K.Unsupported('mask syntax')
            cut = affine(mask[1], compiler)
            if mask[0] == 'lowmask':
                inside, outside = part(row, upper=[cut]), part(row, lower=[cut])
            else:
                cut = K.sub(K.W, cut)
                inside, outside = part(row, lower=[cut]), part(row, upper=[cut])
            if op == 'and':
                visit(inner, inside, depth+1); constant(outside, 0)
            elif op == 'or':
                constant(inside, 1); visit(inner, outside, depth+1)
            else:
                visit(inner, dict(inside, bit=1-inside['bit']), depth+1)
                visit(inner, outside, depth+1)
        else:
            raise K.Unsupported('unsupported counted view: '+repr(op))
    for row in regions(K, kind, number): visit(word, row)
    return rows, constraints, dict(transport_steps=steps[0], input_rows=len(rows), constant_obligations=len(constraints))
