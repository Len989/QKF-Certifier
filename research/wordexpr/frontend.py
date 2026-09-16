"""Fail-closed lexical Java entry and straight-line, long-only expression DAG.

This is not Java name resolution: one uniquely named class, a direct static
long method with one long parameter, and its entire selected body are checked.
Other members are not verified. No method name selects mathematical semantics.
"""
import hashlib
import re

from research.observations.model import digest, require

CONTRACT = 'modular-lsb-word-expressions-v1'
MAX_NODES = 64
MAX_SOURCE = 2_000_000
IDENT = re.compile(r'[A-Za-z_$][A-Za-z0-9_$]*\Z')
# Longest operators matter: x--y must NOT become x - (-y).
LEX = re.compile(r'\s+|//[^\r\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|'
                 r"'(?:\\.|[^'\\])*'|[0-9][A-Za-z0-9_]*|[A-Za-z_$][A-Za-z0-9_$]*|"
                 r'>>>=|>>>|>>=|<<=|>>|<<|\+\+|--|->|==|!=|<=|>=|&&|\|\||'
                 r'[+\-*/&|^%]=|\S')
KEYWORDS = set('abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally float for goto if implements import instanceof int interface long native new package private protected public return short static strictfp super switch synchronized this throw throws transient try void volatile while true false null _'.split())
PREC = {'|': 1, '^': 2, '&': 3, '+': 4, '-': 4}
BINARY = {'|': 'or', '^': 'xor', '&': 'and', '+': 'add', '-': 'sub'}
UNARY = {'~': 'not', '-': 'neg', '+': 'pos'}


class Unsupported(ValueError):
    pass


def need(ok, message):
    if not ok:
        raise Unsupported(message)


def lex(source):
    need(type(source) is str and len(source.encode('utf-8')) <= MAX_SOURCE, 'source byte budget')
    need('"""' not in source, 'text blocks are outside the lexical profile')
    matches = list(LEX.finditer(source))
    result = []
    for m in matches:
        t = m.group()
        need(t not in {'\"', "'"} and not (t == '/' and source.startswith('/*', m.start())), 'terminated lexical literal/comment')
        comment = t.startswith(('//', '/*'))
        # Only the harmless documentation spelling used in OpenJDK is allowed.
        # Other Unicode escapes may change lexical boundaries before tokenizing.
        escapes = re.sub(r'\\u005[Cc]u[0-9A-Fa-f]{4}', '', t) if comment else t
        need('\\u' not in escapes, 'Unicode escape outside the restricted documentation form')
        if not t.isspace() and not comment:
            result.append((t, m.start(), m.end()))
    need(len(result) <= 200_000, 'source token budget')
    return result


def select(source, entry):
    require(type(entry) is dict and set(entry) == {'class', 'method'}, 'explicit entry fields')
    require(all(type(v) is str and IDENT.fullmatch(v) for v in entry.values()), 'entry identifiers')
    ts = lex(source)
    ws = [t[0] for t in ts]
    stack, closes, depths = [], {}, []
    for i, t in enumerate(ws):
        depths.append(len(stack))
        if t == '{':
            stack.append(i)
        elif t == '}':
            need(bool(stack), 'balanced source braces')
            closes[stack.pop()] = i
    need(not stack, 'balanced source braces')
    classes = [i for i in range(len(ws) - 1) if ws[i:i + 2] == ['class', entry['class']]]
    need(len(classes) == 1, 'one explicitly selected lexical class')
    c = classes[0] + 2
    while c < len(ws) and ws[c] not in {'{', ';'}:
        c += 1
    need(c in closes, 'selected class body')
    end, level = closes[c], depths[c] + 1
    candidates = []
    for i in range(c + 1, end):
        if depths[i] != level or ws[i:i + 3] != ['long', entry['method'], '(']:
            continue
        j = i + 3
        if ws[j:j + 1] == ['final']:
            j += 1
        if j + 3 >= end or ws[j] != 'long' or not IDENT.fullmatch(ws[j + 1]) or ws[j + 1] in KEYWORDS or ws[j + 2] != ')':
            continue
        b = j + 3
        need(ws[b] == '{' and b in closes, 'concrete selected method body')
        a = i - 1
        while a > c and ws[a] not in {';', '{', '}'}:
            a -= 1
        prefix = ws[a + 1:i]
        need('static' in prefix and len(prefix) == len(set(prefix)) and
             set(prefix) <= {'public', 'private', 'protected', 'static', 'final'} and
             len(set(prefix) & {'public', 'private', 'protected'}) <= 1,
             'plain static method modifiers; annotations are not supported')
        candidates.append((a + 1, b, closes[b], ws[j + 1], ws[i + 3] == 'final'))
    need(len(candidates) == 1, 'one selected long-to-long method')
    a, b, e, parameter, final_parameter = candidates[0]
    return ws[b + 1:e], parameter, final_parameter, source[ts[a][1]:ts[e][2]], [ts[a][1], ts[e][2]]


class DAG:
    def __init__(self):
        self.nodes = []

    def node(self, op, *args):
        row = [op, *args]
        if row not in self.nodes:
            need(len(self.nodes) < MAX_NODES, 'expression node budget')
            self.nodes.append(row)
        return self.nodes.index(row)


def read_source(source, entry):
    tokens, parameter, final_parameter, declaration, span = select(source, entry)
    need(len(tokens) <= 2048, 'selected body token budget')
    dag, i = DAG(), 0
    env = {parameter: dag.node('input')}
    finals = {parameter} if final_parameter else set()

    def take(expected=None):
        nonlocal i
        need(i < len(tokens) and (expected is None or tokens[i] == expected),
             'unsupported selected-body token at ' + str(i))
        t = tokens[i]
        i += 1
        return t

    def expression(minimum=1, depth=0):
        need(depth < 32, 'expression nesting budget')
        t = take()
        if t in UNARY:
            left = dag.node(UNARY[t], expression(5, depth + 1))
        elif t == '(':
            left = expression(1, depth + 1)
            take(')')
        elif t in env:
            left = env[t]
        elif re.fullmatch(r'(0|[1-9][0-9]*)[lL]', t):
            n = int(t[:-1])
            need(n < 2**63, 'positive decimal long literal range')
            left = dag.node('const', n)
        else:
            raise Unsupported('unsupported word primary: ' + t)
        while i < len(tokens) and PREC.get(tokens[i], 0) >= minimum:
            op = take()
            left = dag.node(BINARY[op], left, expression(PREC[op] + 1, depth + 1))
        return left

    root = None
    while i < len(tokens):
        t = take()
        if t == 'return':
            root = expression()
            take(';')
            need(i == len(tokens), 'one final return; no ignored trailing statements')
            break
        final = t == 'final'
        if final:
            take('long')
            t = 'long'
        declaration_local = t == 'long'
        name = take() if declaration_local else t
        need(IDENT.fullmatch(name) and name not in KEYWORDS and (name not in env if declaration_local else name in env),
             'declared distinct local or known assignment')
        need(name not in finals, 'assignment to final local')
        take('=')
        value = expression()
        take(';')
        env[name] = value
        if final:
            finals.add(name)
    need(root is not None, 'actual return required')
    return {'contract': CONTRACT, 'entry': dict(entry), 'nodes': dag.nodes, 'root': root,
            'source_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(),
            'declaration_sha256': hashlib.sha256(declaration.encode('utf-8')).hexdigest(),
            'span': span}


def goal(spec):
    require(type(spec) is dict and set(spec) == {'schema', 'contract', 'entry', 'target'}, 'goal fields')
    require(spec['schema'] == 'qkf-word-expression-goal-v1' and spec['contract'] == CONTRACT,
            'independent goal contract')
    require(type(spec['entry']) is dict and set(spec['entry']) == {'class', 'method'} and
            all(type(v) is str and IDENT.fullmatch(v) for v in spec['entry'].values()), 'goal entry')
    target = spec['target']
    if target == ['lowest_set_bit']:
        return None
    require(type(target) is list and len(target) == 2 and target[0] == 'equals', 'target kind')
    dag, count = DAG(), 0

    def visit(term, depth=0):
        nonlocal count
        count += 1
        require(depth < 32 and count <= 256 and type(term) is list and term, 'goal expression budget')
        op = term[0]
        require(type(op) is str, 'goal operation')
        if op == 'input':
            require(len(term) == 1, 'input arity')
            return dag.node(op)
        if op == 'const':
            require(len(term) == 2 and type(term[1]) is int and 0 <= term[1] < 2**63, 'goal constant')
            return dag.node(op, term[1])
        arity = 1 if op in UNARY.values() else 2 if op in BINARY.values() else -1
        require(len(term) == arity + 1, 'goal operator/arity')
        return dag.node(op, *(visit(x, depth + 1) for x in term[1:]))

    root = visit(target[1])
    return {'nodes': dag.nodes, 'root': root, 'binding': digest(spec)}
