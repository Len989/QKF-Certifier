"""Semantic vocabulary and source/target-to-ground DAG compilation, no search."""
from research.ground_query.schema import INPUT_SCHEMA, parse, require
from .context import integer

MAX_TERMS = 4096
WORD_ARITY = {'add': 2, 'sub': 2, 'and': 2, 'or': 2, 'xor': 2,
              'not': 1, 'neg': 1, 'pos': 1}
SIGNED = {'<': 'negative', '>=': 'nonnegative', '>': 'positive', '<=': 'nonpositive'}


def signature(ctx):
    sig = {'w.input': {'args': [], 'result': 'Word'}}
    constants = {0, 1} | {row[1] for row in ctx.ir['nodes'] if row[0] == 'const'}
    if ctx.width is not None:
        constants |= {v % (1 << ctx.width) for v in constants}
    for value in constants:
        sig['w.c' + str(value)] = {'args': [], 'result': 'Word'}
    for op, arity in WORD_ARITY.items():
        sig['w.' + op] = {'args': ['Word'] * arity, 'result': 'Word'}
    sig['w.eq'] = {'args': ['Word', 'Word'], 'result': 'Bool'}
    for op in SIGNED.values():
        sig['w.' + op] = {'args': ['Word'], 'result': 'Bool'}
    for op, arity in [('true', 0), ('false', 0), ('not', 1), ('and', 2), ('or', 2), ('xor', 2)]:
        sig['b.' + op] = {'args': ['Bool'] * arity, 'result': 'Bool'}
    for op in SIGNED.values():
        sig['t.' + op] = {'args': [], 'result': 'Bool'}
    for op in ('popcount_eq', 'popcount_le'):
        for k in range(4):
            sig[f't.{op}.{k}'] = {'args': [], 'result': 'Bool'}
    return sig


class Graph:
    def __init__(self, ctx, ground=None):
        self.ctx, self.signature = ctx, signature(ctx)
        self.nodes, self.lookup, self.words, self.atoms = [], {}, {}, {}
        self.sealed = False
        if ground is not None:
            inp = parse(ground)
            require(inp.sorts == ('Word', 'Bool') and inp.signature == self.signature,
                    'ground semantic vocabulary differs')
            for op, args in inp.nodes:
                self.node(op, *args)
            self.sealed = True

    def node(self, op, *args):
        key = (op, tuple(args))
        if key not in self.lookup:
            require(not self.sealed, 'semantic term missing from ground certificate')
            require(len(self.nodes) < MAX_TERMS, 'source ground-term budget')
            require(op in self.signature and len(args) == len(self.signature[op]['args']),
                    'semantic symbol/arity')
            self.lookup[key] = len(self.nodes)
            self.nodes.append({'op': op, 'args': list(args)})
        return self.lookup[key]

    def row(self, i):
        integer(i, 0, len(self.nodes) - 1, 'ground term index')
        row = self.nodes[i]
        return row['op'], tuple(row['args'])

    def literal(self, value):
        require(type(value) is bool, 'Boolean literal')
        return self.node('b.true' if value else 'b.false')

    def word(self, i):
        integer(i, 0, len(self.ctx.ir['nodes']) - 1, 'source word index')
        if i not in self.words:
            row = self.ctx.ir['nodes'][i]
            if row[0] == 'input':
                value = self.node('w.input')
            elif row[0] == 'const':
                value = self.node('w.c' + str(row[1]))
            else:
                value = self.node('w.' + row[0], *(self.word(a) for a in row[1:]))
            self.words[i] = value
        return self.words[i]

    def atom(self, i):
        integer(i, 0, len(self.ctx.ir['atoms']) - 1, 'source atom index')
        if i not in self.atoms:
            atom = self.ctx.ir['atoms'][i]
            if atom['kind'] == 'eq':
                value = self.node('w.eq', self.word(atom['left']), self.word(atom['right']))
            else:
                value = self.node('w.' + SIGNED[atom['op']], self.word(atom['node']))
            self.atoms[i] = value
        return self.atoms[i]

    def source(self, term=None):
        term = self.ctx.ir['formula'] if term is None else term
        if term[0] == 'atom':
            return self.atom(term[1])
        if term[0] == 'literal':
            return self.literal(term[1])
        return self.node('b.' + term[0], *(self.source(c) for c in term[1:]))

    def target(self, term=None):
        term = self.ctx.spec['target'] if term is None else term
        op = term[0]
        if op in ('not', 'and', 'or', 'xor'):
            return self.node('b.' + op, *(self.target(c) for c in term[1:]))
        return self.node('t.' + op + ('.' + str(term[1]) if len(term) == 2 else ''))

    def finish(self, equations, roots, facts):
        needed, stack = set(), [x for pair in [*equations, roots] for x in pair]
        while stack:
            i = stack.pop()
            if i not in needed:
                needed.add(i)
                stack.extend(self.nodes[i]['args'])
        remap = {old: new for new, old in enumerate(sorted(needed))}
        ground = {'schema': INPUT_SCHEMA, 'sorts': ['Word', 'Bool'], 'signature': self.signature,
                  'nodes': [{'op': self.nodes[i]['op'], 'args': [remap[a] for a in self.nodes[i]['args']]}
                            for i in sorted(needed)],
                  'equations': [[remap[a], remap[b]] for a, b in equations],
                  'queries': [[remap[a] for a in roots]]}
        rewritten = [{**f, **({'term': remap[f['term']]} if 'term' in f else {})} for f in facts]
        parse(ground)
        return ground, rewritten
