"""Restricted Java source front end for a descending single-bit OR helper.

The grammar follows the project's earlier source parser. This module does not
execute Java/Python source, import the old comparison vocabulary or accept an
arbitrary Java program. Its word arithmetic profile is explicitly unsigned.
"""
import hashlib
import itertools
import re
from pathlib import Path

from .model import digest, require

TOKEN = re.compile(r'\s+|//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\d+[lL]?|[A-Za-z_$][\w$]*|>>>|>>|<<|>=|<=|==|!=|&&|\|\||\|=|\+=|&=|\^=|\S')
PRECEDENCE = {'||': 1, '&&': 2, '|': 3, '^': 4, '&': 5, '==': 6, '!=': 6,
              '<': 7, '>': 7, '<=': 7, '>=': 7, '<<': 8, '>>': 8, '>>>': 8, '+': 9, '-': 9}
OPS = {'<', '<=', '==', '!=', '>', '>='}
REVERSE = {'<': '>', '<=': '>=', '>': '<', '>=': '<=', '==': '==', '!=': '!='}
PINNED_SOURCE_SHA256 = '1a827adb88f57b8f612979af5b90016077cbf4dad4c54b34e539fee5fce01c95'


def tokens(text):
    return [m for m in TOKEN.finditer(text) if not (m.group().isspace() or m.group().startswith(('//', '/*')))]


def extract_mask(source):
    """Bind the one called word primitive, including its implementation bytes."""
    ts = tokens(source); ws = [m.group() for m in ts]
    starts = [i for i in range(len(ws)) if ws[i:i + 3] == ['class', 'CodeUtil', '{']]
    require(len(starts) == 1, 'one bound CodeUtil primitive class')
    first = starts[0] + 2; depth = 0; end = first
    for end in range(first, len(ws)):
        depth += (ws[end] == '{') - (ws[end] == '}')
        if depth == 0: break
    require(depth == 0, 'closed primitive class')
    methods = [i for i in range(first, end) if ws[i:i + 4] == ['static', 'long', 'mask', '(']]
    require(len(methods) == 1, 'one mask primitive')
    start = methods[0]
    require(ws[start + 4] == 'int' and ws[start + 6:start + 8] == [')', '{'], 'mask primitive signature')
    formal = ws[start + 5]; tail = start + 7; depth = 0
    for tail in range(start + 7, end):
        depth += (ws[tail] == '{') - (ws[tail] == '}')
        if depth == 0: break
    require(depth == 0, 'closed mask primitive')
    canonical = ['width' if w == formal else w for w in ws[start:tail + 1]]
    # Two explicitly delimited implementations of the same low-bit mask.
    # The original shim binding is unchanged. The second form is OpenJDK 25's
    # CodeUtil.mask: on 0..63 modular shift/subtraction gives the low bits; at 64
    # the hexadecimal long literal has all 64 bits set. The assertion is true on 0..64; it is
    # NOT a new caller premise or permission to run Java at unbounded widths.
    # Research all-width claims still use the existing mathematical mask
    # interpretation, not JVM behavior outside its physical domain.
    forms = (
        'static long mask(int width){return width==64 ? -1L : (1L<<width)-1;}',
        'static long mask(int width){assert 0 <= width && width <= 64; '
        'if (width == 64){return 0xffffffffffffffffL;} '
        'else {return (1L << width) - 1;}}',
    )
    require(any(canonical == [m.group() for m in tokens(form)] for form in forms),
            'changed mask primitive requires a new source contract')
    return source[ts[start].start():ts[tail].end()], digest(canonical)


class Parser:
    def __init__(self, text):
        self.tokens = [m.group() for m in tokens(text)]
        self.i = 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self, expected=None):
        t = self.peek()
        require(t is not None and (expected is None or t == expected), 'unsupported Java token: ' + repr(t))
        self.i += 1
        return t

    def expression(self, minimum=1):
        left = self.unary()
        while self.peek() in PRECEDENCE and PRECEDENCE[self.peek()] >= minimum:
            op = self.take()
            left = ('binary', op, left, self.expression(PRECEDENCE[op] + 1))
        return left

    def unary(self):
        if self.peek() in {'!', '~', '-', '+'}:
            return ('unary', self.take(), self.unary())
        if self.peek() == '(':
            self.take(); left = self.expression(); self.take(')')
        else:
            name = self.take()
            if re.fullmatch(r'\d+[lL]?', name):
                digits = name.rstrip('lL')
                require(len(digits) == 1 or not digits.startswith('0'), 'decimal literal required')
                # Java's int shift 1 << p is different from long shift 1L << p.
                # Keep that type distinction in the source contract.
                left = ('number', int(digits), 'long' if name[-1] in 'lL' else 'int')
            elif name in {'true', 'false'}:
                left = ('boolean', name == 'true')
            else:
                require(bool(re.fullmatch(r'[A-Za-z_$][\w$]*', name)), 'unsupported Java primary')
                left = ('name', name)
        while self.peek() in {'.', '('}:
            if self.peek() == '.':
                self.take(); left = ('field', left, self.take())
            else:
                self.take(); args = []
                if self.peek() != ')':
                    args.append(self.expression())
                    while self.peek() == ',':
                        self.take(); args.append(self.expression())
                self.take(')'); left = ('call', left, tuple(args))
        return left

    def statement(self):
        t = self.peek()
        if t == '{':
            self.take(); rows = []
            while self.peek() != '}':
                rows.append(self.statement())
            self.take(); return ('block', tuple(rows))
        if t == 'for':
            self.take(); self.take('('); typ = self.take(); name = self.take(); self.take('=')
            start = self.expression(); self.take(';'); condition = self.expression(); self.take(';')
            target = self.take(); step = self.take(); self.take(step); self.take(')')
            require(typ == 'int' and step in {'+', '-'}, 'integer unit traversal')
            return ('for', name, start, condition, target, step, self.statement())
        if t == 'if':
            self.take(); self.take('('); condition = self.expression(); self.take(')')
            yes = self.statement(); no = ('block', ())
            if self.peek() == 'else':
                self.take(); no = self.statement()
            return ('if', condition, yes, no)
        if t == 'return':
            self.take(); value = self.expression(); self.take(';'); return ('return', value)
        if t == 'assert':
            self.take(); condition = self.expression()
            if self.peek() == ':':
                self.take()
                while self.peek() != ';':
                    self.take()
            self.take(';'); return ('assert', condition)
        if t == 'final':
            self.take(); t = self.peek()
        if t in {'long', 'int', 'boolean'}:
            typ = self.take(); name = self.take(); self.take('='); value = self.expression(); self.take(';')
            return ('declare', typ, name, value)
        name = self.take(); op = self.take()
        kinds = {'|=': 'or_assign', '+=': 'add_assign', '&=': 'and_assign',
                 '^=': 'xor_assign', '=': 'assign'}
        require(op in kinds, 'supported assignment operator')
        value = self.expression(); self.take(';')
        return (kinds[op], name, value)


def extract_declaration(source, method, types):
    """Locate one typed method without requiring its whole body to be supported."""
    ts = tokens(source); words = [m.group() for m in ts]
    prefix = ['private', 'static', 'long', method, '(']
    starts = [i for i in range(len(words)) if words[i:i + len(prefix)] == prefix]
    require(len(starts) == 1, 'one real ' + method + ' declaration')
    first = starts[0]; i = first + len(prefix); parameters = []
    while words[i] != ')':
        typ, name = words[i:i + 2]; parameters.append((typ, name)); i += 2
        require(words[i] in {',', ')'}, 'typed Java parameters')
        if words[i] == ',': i += 1
    require([t for t, _ in parameters] == types, 'helper ABI')
    require(all(re.fullmatch(r'[A-Za-z_$][\w$]*', n) for _, n in parameters), 'formal identifiers')
    require(len({n for _, n in parameters}) == len(types), 'distinct formal parameters')
    i += 1; require(words[i] == '{', 'helper body'); start = i; depth = 0
    for end in range(start, len(words)):
        depth += (words[end] == '{') - (words[end] == '}')
        if depth == 0: break
    require(depth == 0, 'closed helper body')
    body = source[ts[start].start():ts[end].end()]
    return [n for _, n in parameters], body, source[ts[first].start():ts[end].end()]


def extract_method(source):
    names, body, helper = extract_declaration(source, 'setOptionalBits', ['int', 'long', 'long', 'long', 'long'])
    parser = Parser(body); ast = parser.statement(); require(parser.peek() is None, 'complete helper parse')
    return names, ast, helper


def normal(node, aliases):
    if not isinstance(node, tuple): return node
    if node[0] == 'name': return ('name', aliases.get(node[1], node[1]))
    if node[:1] == ('binary',) and node[1] in {'&', '|', '&&', '||'}:
        op = node[1]; parts = []
        def collect(n):
            if isinstance(n, tuple) and n[:2] == ('binary', op): collect(n[2]); collect(n[3])
            else: parts.append(normal(n, aliases))
        collect(node[2]); collect(node[3])
        return ('commutative', op, tuple(sorted(parts, key=repr)))
    return tuple(normal(x, aliases) if isinstance(x, tuple) and x else x for x in node)


def template(text):
    p = Parser(text); result = p.expression(); require(p.peek() is None, 'internal expression template')
    return normal(result, {})


def read_source(source):
    names, ast, helper = extract_method(source)
    _, mask_hash = extract_mask(source)
    require(ast[0] == 'block', 'helper block')
    body = [s for s in ast[1] if s[0] != 'assert']
    assertions = [s for s in ast[1] if s[0] == 'assert']
    require(len(body) == 4 and len(assertions) == 1, 'supported complete helper shape and input condition')
    optional, value, loop, ret = body
    aliases = dict(zip(names, ['arg0', 'arg1', 'arg2', 'arg3', 'arg4']))
    require(optional[:2] == ('declare', 'long') and value[:2] == ('declare', 'long'), 'word local declarations')
    require(normal(optional[3], aliases) == template('arg3 & ~arg2 & CodeUtil.mask(arg0 - 1)'), 'nonsign optional mask')
    require(optional[2] not in aliases, 'no shadowed optional local'); aliases[optional[2]] = 'optional'
    require(normal(assertions[0][1], aliases) == template('(arg4 & optional) == 0'), 'declared disjoint seed condition')
    require(normal(value[3], aliases) == template('arg4') and value[2] not in aliases, 'initial word binding')
    aliases[value[2]] = 'value'
    require(loop[0] == 'for' and loop[1] == loop[4] and loop[5] == '-' and loop[1] not in aliases,
            'descending single-write traversal')
    require(normal(loop[2], aliases) == template('arg0 - 1'), 'initial source bit')
    aliases[loop[1]] = 'position'
    condition = normal(loop[3], aliases)
    require(condition in [template('position >= 0'), template('0 <= position')], 'complete traversal to zero')
    require(loop[6][0] == 'block' and len(loop[6][1]) == 2, 'one bit declaration and one decision')
    bit, branch = loop[6][1]
    require(bit[:2] == ('declare', 'long') and normal(bit[3], aliases) == template('1L << position')
            and bit[2] not in aliases, 'single current-bit mask')
    aliases[bit[2]] = 'bit'
    require(branch[0] == 'if' and branch[3] == ('block', ()), 'single optional update')
    update = branch[2]
    if update[0] == 'block':
        require(len(update[1]) == 1, 'one write in branch'); update = update[1][0]
    require(update[0] == 'or_assign' and aliases.get(update[1]) == 'value'
            and normal(update[2], aliases) == template('bit'), 'single-bit OR write')
    require(ret[0] == 'return' and normal(ret[1], aliases) == template('value'), 'return updated word')
    tests = []; right_words = set()

    def affine(n):
        if n[0] == 'binary' and n[1] in {'+', '-'} and n[3][0] == 'number':
            core, offset = affine(n[2]); offset += n[3][1] * (1 if n[1] == '+' else -1)
            require(abs(offset) <= 1 << 30, 'source offset budget')
            return core, offset
        return normal(n, aliases), 0

    def guard(n):
        if n[0] == 'unary' and n[1] == '!': return ['not', guard(n[2])]
        require(n[0] == 'binary', 'supported Boolean source guard')
        op = n[1]
        if op in {'&&', '||'}: return ['and' if op == '&&' else 'or', guard(n[2]), guard(n[3])]
        a, b = normal(n[2], aliases), normal(n[3], aliases)
        if op in {'==', '!='} and {repr(a), repr(b)} == {repr(template('optional & bit')), repr(template('0'))}:
            return ['optional'] if op == '!=' else ['not', ['optional']]
        require(op in OPS, 'word comparison operator')
        (a, x), (b, y) = affine(n[2]), affine(n[3])
        trial = template('value | bit')
        if b == trial:
            a, b, x, y, op = b, a, y, x, REVERSE[op]
        require(a == trial and b[0] == 'name' and b[1] in {'arg1', 'arg2', 'arg3', 'arg4'},
                'one OR trial compared with an immutable input word')
        right_words.add(b[1]); test = {'op': op, 'offset': y - x}
        if test not in tests: tests.append(test)
        return ['test', tests.index(test)]

    decision = guard(branch[1])
    require(len(right_words) == 1 and 0 < len(tests) <= 8, 'one shared comparison word-pair')
    right = next(iter(right_words)); right_index = int(right[-1]) - 1
    columns = {}
    for inputs in itertools.product((0, 1), repeat=4):
        bound, must, may, initial = inputs
        o = may & (1 - must)
        if initial & o: continue
        for y in range(initial, initial + o + 1):
            column = f'{initial}{o}{inputs[right_index]}{y}'
            columns.setdefault(column, list(inputs))
    # Split rules use source term identity: OR with the current one-bit mask
    # preserves both outside slices; descending writes leave the lower seed.
    higher = ['slice', ['output', 'value'], 'higher']
    lower = ['slice', ['input', 'arg4'], 'lower']
    bound_slices = {part: ['slice', ['input', right], part] for part in ['higher', 'bit', 'lower']}
    return {'schema': 'qkf-descending-word-source-v1', 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'helper_sha256': hashlib.sha256(helper.encode()).hexdigest(), 'parsed_sha256': digest(ast),
            'primitive_bindings': {'CodeUtil.mask': mask_hash},
            'guard': decision, 'tests': tests, 'comparison_word': right,
            'columns': [{'symbol': a, 'input_bits': inputs} for a, inputs in sorted(columns.items())],
            'wiring': {'rules': ['descending-outside-write', 'or-one-bit-slices'],
                       'trial': {'higher': higher, 'bit': 1, 'lower': lower},
                       'through': {'higher': higher, 'bit': ['proposed_bit']},
                       'lower_control': {'left': lower, 'right': bound_slices['lower']},
                       'right_slices': bound_slices},
            'profile': 'unsigned mathematical payload; fixed zero sign bit; disjoint initial and optional masks'}


def pinned_source():
    path = Path(__file__).resolve().parents[1] / 'graal/native/IntegerStamp.java'
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == PINNED_SOURCE_SHA256, 'pinned Java source changed')
    return raw.decode()
