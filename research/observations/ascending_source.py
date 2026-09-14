"""Restricted ascending region frontend, sharing the Java lexer/parser.

This selects a lexical loop region, not a proof of computeLowerBound's caller
or of the path reaching that region. Entry words/masks are supplied separately.
No carry phase, quotient, source_cell, or per-program repair action is imported.
"""
import hashlib

from .java_words import Parser, extract_declaration, extract_mask, normal, template, tokens
from .model import require

PROFILE = {
    'entry': 'positive payload width w; 0 <= must, seed, may < 2^w; must subset seed subset may',
    'scan': 'positions 0 through w-1; Java bits parameter is w+1',
    'answer': 'low w output bits only; terminal registers and higher word are unobserved',
    'semantics': 'mathematical nonnegative words; surrounding helper control flow is outside this region',
}


def _parsed(text):
    p = Parser(text); ast = p.statement()
    require(p.peek() is None, 'complete region statement')
    return ast


def extract_region(source):
    names, body, _ = extract_declaration(source, 'computeLowerBound',
                                          ['int', 'long', 'long', 'long', 'boolean'])
    mask, mask_hash = extract_mask(source)
    ts = tokens(body); ws = [m.group() for m in ts]
    aliases = dict(zip(names, ['width', 'bound', 'must', 'may', 'can_zero']))
    candidates = []
    for i, w in enumerate(ws):
        if w != 'for' or ws[i + 1] != '(': continue
        # The selected region must start at zero. Other helper loops are not parsed.
        j = i + 2
        while ws[j] != ';': j += 1
        start = ws[i + 2:j]
        if len(start) != 4 or start[0] != 'int' or start[2:] != ['=', '0']: continue
        j += 1
        while ws[j] != '{': j += 1
        depth = 0
        for end in range(j, len(ws)):
            depth += (ws[end] == '{') - (ws[end] == '}')
            if depth == 0: break
        require(depth == 0, 'closed ascending loop')
        code = body[ts[i].start():ts[end].end()]
        loop = _parsed(code)
        require(loop[0] == 'for' and loop[1] == loop[4] and loop[5] == '+', 'ascending unit scan')
        require(loop[1] not in aliases, 'distinct position local')
        local = {**aliases, loop[1]: 'position'}
        require(normal(loop[3], local) in [template('position < width - 1'), template('width - 1 > position')],
                'exact nonsign scan extent')
        # Persistent Boolean declarations immediately preceding the loop.
        begin = i; declarations = []
        while begin >= 5 and ws[begin - 5] == 'boolean' and ws[begin - 1] == ';':
            require(begin == 5 or ws[begin - 6] != 'final', 'mutable region Boolean register')
            decl = _parsed(body[ts[begin - 5].start():ts[begin - 1].end()])
            require(decl[:2] == ('declare', 'boolean') and decl[3][0] == 'boolean',
                    'literal initial Boolean register')
            declarations.insert(0, decl); begin -= 5
        require(0 < len(declarations) <= 4, 'one to four region Boolean registers')
        candidates.append((loop, declarations, body[ts[begin].start():ts[end].end()], local))
    require(len(candidates) == 1, 'one zero-based ascending region')
    loop, declarations, code, aliases = candidates[0]
    optional = []
    for i, w in enumerate(ws):
        if w != 'long' or ws[i + 2] != '=': continue
        j = i + 3
        while ws[j] != ';': j += 1
        try: decl = _parsed(body[ts[i].start():ts[j].end()])
        except ValueError: continue
        if normal(decl[3], aliases) == template('may & ~must & CodeUtil.mask(width - 1)'):
            begin = i - 1 if i and ws[i - 1] == 'final' else i
            optional.append((decl, body[ts[begin].start():ts[j].end()]))
    require(len(optional) == 1, 'one bound optional mask declaration')
    optional_decl, optional_code = optional[0]
    require(optional_decl[2] not in aliases, 'distinct optional mask local')
    aliases[optional_decl[2]] = 'optional'
    for j, decl in enumerate(declarations):
        require(decl[2] not in aliases, 'distinct Boolean register')
        aliases[decl[2]] = 'register' + str(j)
    require(loop[6][0] == 'block' and len(loop[6][1]) >= 2, 'bit declaration and loop operations')
    bit, *statements = loop[6][1]
    require(bit[:2] == ('declare', 'long') and normal(bit[3], aliases) == template('1L << position')
            and bit[2] not in aliases, 'long current-bit mask')
    aliases[bit[2]] = 'bit'

    def writes(s):
        if s[0] == 'block': return set().union(*(writes(x) for x in s[1]))
        if s[0] == 'if': return writes(s[2]) | writes(s[3])
        return {s[1]} if s[0].endswith('assign') and s[1] not in aliases else set()

    targets = set().union(*(writes(s) for s in statements))
    require(len(targets) == 1, 'one mutable region word')
    word = next(iter(targets)); aliases[word] = 'value'
    # The selected word is an existing long local, but its entry value is a
    # region parameter: we do not infer the outer helper's path preconditions.
    word_declarations = [i for i in range(len(ws) - 2) if ws[i:i + 3] == ['long', word, '=']]
    require(len(word_declarations) == 1 and (word_declarations[0] == 0 or ws[word_declarations[0] - 1] != 'final'),
            'one mutable declared region word')
    return {'names': names, 'loop': loop, 'declarations': declarations, 'statements': statements,
            'aliases': aliases, 'word': word, 'code': code, 'optional_code': optional_code,
            'mask': mask, 'mask_hash': mask_hash}


def read_source(source):
    region = extract_region(source); aliases = region['aliases']; rules = set()

    def guard(n):
        if n[0] == 'boolean': return ['literal', n[1]]
        if n[0] == 'name' and aliases.get(n[1], '').startswith('register'):
            return ['register', int(aliases[n[1]][8:])]
        if n[:2] == ('unary', '!'): return ['not', guard(n[2])]
        if n[0] == 'binary' and n[1] in {'&&', '||'}:
            return ['and' if n[1] == '&&' else 'or', guard(n[2]), guard(n[3])]
        require(n[0] == 'binary' and n[1] in {'==', '!='}, 'local Boolean or masked-bit test')
        a, b = normal(n[2], aliases), normal(n[3], aliases)
        zero = template('0')
        if a == zero: a, b = b, a
        require(b == zero, 'masked-bit comparison with zero')
        for operand in ['must', 'may', 'optional', 'value']:
            if a == template(operand + ' & bit'):
                return ['bit', operand, n[1] == '!=']
        raise ValueError('guard observes an unsupported word slice')

    def coefficient(n):
        if normal(n, aliases) == template('bit'): return 1
        if n[0] == 'number' and n[1] == 0: return 0
        if n[:2] == ('binary', '+'): return coefficient(n[2]) + coefficient(n[3])
        if n[:2] == ('binary', '<<') and n[3][0] == 'number' and 0 <= n[3][1] <= 3:
            return coefficient(n[2]) << n[3][1]
        raise ValueError('addition must be a nonnegative constant multiple of the current bit')

    def statement(s):
        if s[0] == 'block': return ['block', [statement(x) for x in s[1]]]
        if s[0] == 'if': return ['if', guard(s[1]), statement(s[2]), statement(s[3])]
        target = aliases.get(s[1])
        if s[0] == 'assign' and target and target.startswith('register'):
            return ['register_set', int(target[8:]), guard(s[2])]
        require(target == 'value', 'only region word and Boolean register writes')
        kind, value = s[0], s[2]
        # Ordinary assignment and compound assignment share the same rules.
        if kind == 'assign':
            require(value[0] == 'binary' and value[1] in {'+', '|', '&', '^'}, 'local word assignment')
            a, b = value[2], value[3]
            if normal(b, aliases) == template('value'): a, b = b, a
            require(normal(a, aliases) == template('value'), 'same word on assignment input')
            kind = {'+': 'add_assign', '|': 'or_assign', '&': 'and_assign', '^': 'xor_assign'}[value[1]]
            value = b
        if kind == 'add_assign':
            k = coefficient(value); require(0 <= k <= 8, 'local addition coefficient budget')
            rules.add('add-current-bit'); return ['add', k]
        op = {'or_assign': 'set', 'and_assign': 'clear', 'xor_assign': 'flip'}.get(kind)
        require(op is not None and normal(value, aliases) == template('~bit' if op == 'clear' else 'bit'),
                'one-bit Boolean write')
        rules.add(op + '-current-bit'); return [op]

    body = ['block', [statement(s) for s in region['statements']]]
    return {'schema': 'qkf-ascending-region-source-v1',
            'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'region_sha256': hashlib.sha256(region['code'].encode()).hexdigest(),
            'primitive_bindings': {'CodeUtil.mask': region['mask_hash']},
            'register_initial': [s[3][1] for s in region['declarations']], 'body': body,
            'rules': ['euclidean-bit-split', 'fixed-low-prefix', *sorted(rules)],
            'profile': dict(PROFILE)}
