"""Independent finite semantics for the symbolic-obligation DSL.

This evaluator deliberately imports neither the symbolic compiler nor its
arithmetic/certificate helpers. Scalars are Python mathematical integers;
words have the declared positive width. It is a finite oracle, not a proof.
"""

DSL = 'qkf-symbolic-bit-obligation-v1'


class UnsupportedConcrete(ValueError):
    pass


def count_bits(kind, value, width):
    """Count directly from the requested end; zero/all-one counts may be w."""
    if kind not in {'clz', 'clo', 'ctz', 'cto'}:
        raise UnsupportedConcrete('count kind ' + repr(kind))
    wanted = 1 if kind in {'clo', 'cto'} else 0
    leading = kind in {'clz', 'clo'}
    count = 0
    while count < width:
        position = width - count - 1 if leading else count
        if ((value >> position) & 1) != wanted:
            break
        count += 1
    return count


def eval_scalar(expr, width, inputs, parameters=None):
    parameters = {} if parameters is None else parameters
    if type(expr) is int:
        return expr
    if isinstance(expr, str):
        if expr == 'w':
            return width
        if expr not in parameters:
            raise UnsupportedConcrete('scalar name ' + expr)
        return parameters[expr]
    if not isinstance(expr, (list, tuple)) or not expr:
        raise UnsupportedConcrete('scalar syntax ' + repr(expr))
    op = expr[0]
    if op in {'clz', 'clo', 'ctz', 'cto'} and len(expr) == 2:
        value=inputs[expr[1]] if isinstance(expr[1],str) and expr[1] in inputs else eval_word(expr[1],width,inputs,parameters)
        return count_bits(op,value,width)
    if op == 'ite' and len(expr) == 4:
        arm = expr[2] if eval_boolean(expr[1], width, inputs, parameters) else expr[3]
        return eval_scalar(arm, width, inputs, parameters)
    if op in {'add', 'sub', 'min', 'max'} and len(expr) == 3:
        left = eval_scalar(expr[1], width, inputs, parameters)
        right = eval_scalar(expr[2], width, inputs, parameters)
        if op == 'add':
            return left + right
        if op == 'sub':
            return left - right
        if op == 'min':
            return min(left, right)
        return max(left, right)
    raise UnsupportedConcrete('scalar operation ' + repr(expr))


def eval_boolean(expr, width, inputs, parameters=None):
    if type(expr) is bool:
        return expr
    if not isinstance(expr, (list, tuple)) or not expr:
        raise UnsupportedConcrete('Boolean syntax ' + repr(expr))
    op = expr[0]
    if op in {'and', 'or'}:
        values = [eval_boolean(x, width, inputs, parameters) for x in expr[1:]]
        return all(values) if op == 'and' else any(values)
    if op == 'not' and len(expr) == 2:
        return not eval_boolean(expr[1], width, inputs, parameters)
    if op in {'le', 'lt', 'eq'} and len(expr) == 3:
        left = eval_scalar(expr[1], width, inputs, parameters)
        right = eval_scalar(expr[2], width, inputs, parameters)
        if op == 'le':
            return left <= right
        if op == 'lt':
            return left < right
        return left == right
    raise UnsupportedConcrete('Boolean operation ' + repr(expr))


def eval_word(expr, width, inputs, parameters=None):
    if not isinstance(expr, (list, tuple)) or not expr:
        raise UnsupportedConcrete('word syntax ' + repr(expr))
    mask = (1 << width) - 1
    op = expr[0]
    if op == 'input' and len(expr) == 2 and expr[1] in inputs:
        return inputs[expr[1]]
    if op == 'zero' and len(expr) == 1:
        return 0
    if op == 'ones' and len(expr) == 1:
        return mask
    if op == 'not' and len(expr) == 2:
        return mask ^ eval_word(expr[1], width, inputs, parameters)
    if op == 'reverse' and len(expr) == 2:
        value=eval_word(expr[1],width,inputs,parameters)
        return sum(((value >> index) & 1) << (width-index-1) for index in range(width))
    if op in {'and', 'or', 'xor'} and len(expr) == 3:
        left = eval_word(expr[1], width, inputs, parameters)
        right = eval_word(expr[2], width, inputs, parameters)
        return (left & right) if op == 'and' else ((left | right) if op == 'or' else (left ^ right))
    if op in {'lowmask', 'highmask'} and len(expr) == 2:
        count = max(0, min(width, eval_scalar(expr[1], width, inputs, parameters)))
        low = (1 << count) - 1
        return low if op == 'lowmask' else low << (width - count)
    if op in {'shl', 'lshr'} and len(expr) == 3:
        value = eval_word(expr[1], width, inputs, parameters)
        amount = eval_scalar(expr[2], width, inputs, parameters)
        if amount < 0 or amount >= width:
            return 0
        return ((value << amount) & mask) if op == 'shl' else value >> amount
    if op == 'ite' and len(expr) == 4:
        arm = expr[2] if eval_boolean(expr[1], width, inputs, parameters) else expr[3]
        return eval_word(arm, width, inputs, parameters)
    raise UnsupportedConcrete('word operation ' + repr(expr))


def word_bit(value, index, width):
    return (value >> index) & 1 if 0 <= index < width else 0


def evaluate_case(source, width, inputdict, paramdict=None):
    """Evaluate assumptions and full claims; failures are actual finite witnesses."""
    paramdict = {} if paramdict is None else paramdict
    if source.get('schema') != DSL:
        raise ValueError('DSL schema')
    if type(width) is not int or width < 1:
        raise ValueError('positive integer width required')
    if set(inputdict) != set(source['inputs']):
        raise ValueError('input names')
    if set(paramdict) != set(source.get('parameters', [])):
        raise ValueError('parameter names')
    if any(type(x) is not int or not 0 <= x < (1 << width) for x in inputdict.values()):
        raise ValueError('word value outside width')
    if any(type(x) is not int for x in paramdict.values()):
        raise ValueError('integer parameters required')
    applicable = eval_boolean(source.get('assume', True), width, inputdict, paramdict)
    claims, values = [], []
    for claim in source['claims']:
        op = claim[0]
        if op == 'word_eq' and len(claim) == 3:
            left = eval_word(claim[1], width, inputdict, paramdict)
            right = eval_word(claim[2], width, inputdict, paramdict)
            claims.append(left == right)
            values.append({'left': left, 'right': right})
        elif op == 'bit_is' and len(claim) == 4 and type(claim[3]) is int and claim[3] in (0, 1):
            word = eval_word(claim[1], width, inputdict, paramdict)
            index = eval_scalar(claim[2], width, inputdict, paramdict)
            actual = word_bit(word, index, width)
            claims.append(actual == claim[3])
            values.append({'word': word, 'index': index, 'bit': actual, 'expected': claim[3]})
        elif op == 'scalar' and len(claim) == 2:
            actual = eval_boolean(claim[1], width, inputdict, paramdict)
            claims.append(actual)
            values.append({'predicate': actual})
        else:
            raise UnsupportedConcrete('claim syntax ' + repr(claim))
    return {'applicable': applicable, 'claims': claims, 'values': values,
            'counterexample': applicable and not all(claims)}
