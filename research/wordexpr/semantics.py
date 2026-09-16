"""General LSB cut rules. Arithmetic residuals are not program-specific states.

For every arithmetic node, total = operand bits (+/-) + incoming carry;
total = (total % 2) + 2*(total // 2), including negative borrows.
Final carries are discarded in modular word semantics. No fixed width is
used to discover states. Constants emit their successive binary digits.
"""
from research.observations.model import MODEL_SCHEMA, Model, integer, require


def initial(ir):
    return tuple(n[1] if n[0] == 'const' else 0 for n in ir['nodes'])


def valid_state(ir, state):
    require(type(state) in {tuple, list} and len(state) == len(ir['nodes']), 'residual vector')
    for n, s in zip(ir['nodes'], state):
        op = n[0]
        lo, hi = (-1, 0) if op in {'sub', 'neg'} else (0, 1) if op == 'add' else (0, n[1]) if op == 'const' else (0, 0)
        require(integer(s, lo, hi), 'typed arithmetic residual')
    return tuple(state)


def cell(ir, state, symbol):
    require(type(symbol) is str and symbol in {'0', '1'}, 'complete binary input column')
    values, next_state = [], []
    for n, carry in zip(ir['nodes'], state):
        op, rest = n[0], n[1:]
        following = 0
        if op == 'input':
            bit = int(symbol)
        elif op == 'const':
            bit, following = carry % 2, carry // 2
        else:
            a = values[rest[0]]
            b = values[rest[1]] if len(rest) == 2 else 0
            if op in {'add', 'sub', 'neg'}:
                total = carry + (a + b if op == 'add' else a - b if op == 'sub' else -a)
                bit, following = total % 2, total // 2
            elif op == 'not':
                bit = 1 - a
            elif op == 'pos':
                bit = a
            elif op == 'and':
                bit = a & b
            elif op == 'or':
                bit = a | b
            elif op == 'xor':
                bit = a ^ b
            else:
                raise ValueError('unknown compiled operation')
        values.append(bit)
        next_state.append(following)
    return str(values[ir['root']]), tuple(next_state)


def evaluate(ir, x, width):
    """Separate whole-integer evaluation, not execution of the bit transition."""
    require(integer(width, 1, 4096) and integer(x, 0, (1 << width) - 1), 'word input')
    mask, values = (1 << width) - 1, []
    for n in ir['nodes']:
        op = n[0]
        if op == 'input':
            v = x
        elif op == 'const':
            v = n[1]
        else:
            a = values[n[1]]
            b = values[n[2]] if len(n) == 3 else 0
            if op == 'neg': v = -a
            elif op == 'pos': v = a
            elif op == 'not': v = ~a
            elif op == 'add': v = a + b
            elif op == 'sub': v = a - b
            elif op == 'and': v = a & b
            elif op == 'or': v = a | b
            elif op == 'xor': v = a ^ b
            else: raise ValueError('unknown integer operation')
        values.append(v & mask)
    return values[ir['root']]


def model(ir, states):
    names = {s: 's' + str(i) for i, s in enumerate(states)}
    rows = []
    for s in states:
        for a in ('0', '1'):
            y, nxt = cell(ir, s, a)
            require(nxt in names, 'source carrier closure')
            rows.append({'state': names[s], 'symbol': a, 'output': y, 'next': names[nxt]})
    return Model({'schema': MODEL_SCHEMA, 'states': list(names.values()), 'alphabet': ['0', '1'],
                  'outputs': ['0', '1'], 'initial': names[initial(ir)],
                  'terminal': {v: 'discard-final-carries' for v in names.values()},
                  'steps': rows, 'binding': {'source_ir': ir}}).data


def goal_initial(target):
    return (0,) if target is None else initial(target)


def goal_cell(target, state, a):
    if target is not None:
        return cell(target, state, a)
    # Independent positional definition: emit the first input 1 only.
    seen = state[0]
    return str(int(a) if not seen else 0), (int(bool(seen or a == '1')),)


def goal_value(target, x, width):
    if target is not None:
        return evaluate(target, x, width)
    for k in range(width):
        if (x >> k) & 1:
            return 1 << k
    return 0
