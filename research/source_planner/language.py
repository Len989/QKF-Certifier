"""Syntax-only bounded candidate generation and sufficient consumer pullbacks.

No native rule evaluation, source execution, fixtures or expected outcomes here.
The checked finite model orders questions; it never supplies a source fact.
"""
from research.source_query.encoding import Graph, SIGNED
from .context import digest, require

LOCAL = {'b.not', 'b.and', 'b.or', 'b.xor', 'w.eq', 'w.pos', 'w.neg', 'w.not',
         'w.add', 'w.sub', 'w.and', 'w.or', 'w.xor', 't.nonnegative', 't.positive',
         't.nonpositive', 't.popcount_le.0'}


class State:
    def __init__(self, ctx, audit):
        self.ctx, self.audit, self.graph = ctx, audit, Graph(ctx)
        self.roots = (self.graph.source(), self.graph.target())
        self.facts, self.equations, self.replacements = [], [], {}
        self.tried, self.pairs = set(), set()
        self.version, self.live_model, self.live_checkpoint = 0, None, None

    def views(self):
        g, memo, active = self.graph, {}, set()

        def view(i):
            if i in memo:
                return memo[i]
            require(i not in active, 'acyclic native rewrite guidance')
            active.add(i)
            if i in self.replacements:
                result = view(self.replacements[i])
            else:
                op, args = g.row(i)
                current = g.node(op, *(view(a) for a in args))
                result = view(current) if current in self.replacements else current
            active.remove(i)
            memo[i] = result
            return result
        return view

    def bridge_symbol(self, atom):
        obj, nodes = self.ctx.ir['atoms'][atom], self.ctx.ir['nodes']
        if obj['kind'] == 'signed_zero' and nodes[obj['node']] == ['input']:
            return 't.' + SIGNED[obj['op']]
        if obj['kind'] == 'eq':
            for a, b in ((obj['left'], obj['right']), (obj['right'], obj['left'])):
                if nodes[a] == ['input'] and nodes[b] == ['const', 0]:
                    return 't.popcount_eq.0'
        return None

    def next_question(self):
        g, view = self.graph, self.views()
        source, target = map(view, self.roots)
        raw_target_op = g.row(self.roots[1])[0]
        atom_ids = {term: atom for atom, term in g.atoms.items()}
        word_ids = {term: node for node, term in g.words.items()}
        visited, pure_cache, model_cache = set(), {}, {}

        def pure_target(i):
            if i not in pure_cache:
                op, args = g.row(i)
                pure_cache[i] = op.startswith('t.') or op in ('b.true', 'b.false') or (
                    op in ('b.not', 'b.and', 'b.or', 'b.xor') and all(pure_target(a) for a in args))
            return pure_cache[i]

        def model_value(i):
            if self.live_model is None:
                return None
            if i not in model_cache:
                self.audit.counts['separator_term_evaluations'] += 1
                op, args = g.row(i)
                desc = self.live_model['operations'][op]
                key = tuple(model_value(a) for a in args)
                table = {tuple(r['args']): r['value'] for r in desc['rows']}
                model_cache[i] = table.get(key, desc['default'])
            return model_cache[i]

        def candidate(rule, origin, **fields):
            self.audit.counts['candidate_proposals'] += 1
            return dict(rule=rule, **fields), origin

        def walk(original, desired, path, origin_kind):
            current = view(original)
            key = current, desired
            if key in visited or current == desired:
                return
            visited.add(key)
            self.audit.counts['candidate_syntax_visits'] += 1
            op, args = g.row(current)
            if op in ('b.true', 'b.false'):
                return
            origin = dict(kind=origin_kind, path=path, term=original,
                          normalized_term=current, demanded_term=desired, via=origin_kind)
            # The question is extracted from an actual source implication,
            # not from all pairs of predicates and not from its hoped-for truth.
            old_op, old_args = g.row(original)
            for template in dict.fromkeys((original, current)):
                top, children = g.row(template)
                if top == 'b.or' and len(children) == 2:
                    left_op, left_args = g.row(children[0])
                    if left_op == 'b.not' and left_args[0] in atom_ids and children[1] in atom_ids:
                        yield candidate('eq-mask', dict(origin, kind='source_relational_template', template=template),
                                        antecedent=atom_ids[left_args[0]], consequent=atom_ids[children[1]])
            if op in LOCAL or (op.startswith('w.c') and self.ctx.width is not None):
                yield candidate('local', origin, term=current)
            if pure_target(current):
                yield candidate('guard-truth', dict(origin, kind='guarded_target_question'), term=current)
            atom_term = current if current in atom_ids else original
            if atom_term in atom_ids and self.bridge_symbol(atom_ids[atom_term]) is not None:
                yield candidate('input-bridge', dict(origin, kind='source_input_bridge'), atom=atom_ids[atom_term])
            word_term = current if current in word_ids else original
            if word_term in word_ids and not op.startswith('w.c'):
                node = word_ids[word_term]
                row = self.ctx.ir['nodes'][node]
                if row[0] == 'and' and any(self.ctx.ir['nodes'][a] == ['const', 1] for a in row[1:]):
                    yield candidate('low-bit', dict(origin, kind='word_IR_dependency', ir_node=node), masked_node=node)
            if op == 'w.input':
                yield candidate('guard-zero', dict(origin, kind='guarded_source_input'))
            children = old_args if old_op == op and original not in self.replacements else args
            demands = [None] * len(children)
            pullback = 'IR_dependency'
            if desired is not None:
                dop, dargs = g.row(desired)
                if op == dop and len(args) == len(dargs):
                    demands = list(dargs)
                    pullback = 'sufficient_congruence_pullback'
                elif op in ('b.and', 'b.or') and dop in ('b.true', 'b.false'):
                    demands = [desired] * len(children)
                    pullback = 'sufficient_Boolean_pullback'
                elif op == 'b.not' and dop in ('b.true', 'b.false'):
                    demands = [g.literal(dop == 'b.false')]
                    pullback = 'sufficient_Boolean_pullback'
                elif op in ('b.and', 'b.or'):
                    for j, arg in enumerate(args):
                        if arg == desired:
                            demands[1-j] = g.literal(op == 'b.and')
                            demands[j] = desired
                            pullback = 'sufficient_Boolean_pullback'
            order = list(range(len(children)))
            if pullback == 'sufficient_congruence_pullback' and self.live_model is not None:
                order.sort(key=lambda j: (model_value(args[j]) == model_value(demands[j]), j))
            for j in order:
                yield from walk(children[j], demands[j], path + [j], pullback)

        def proposals():
            # A direct consumer-shaped bridge wins over speculative unfolding.
            for atom, term in sorted(g.atoms.items()):
                self.audit.counts['candidate_syntax_visits'] += 1
                if self.bridge_symbol(atom) == raw_target_op:
                    yield candidate('input-bridge', dict(kind='consumer_matching_bridge',
                                    source_atom=atom, consumer_term=self.roots[1]), atom=atom)
            if g.row(target)[0] not in ('b.true', 'b.false'):
                yield candidate('guard-truth', dict(kind='independent_consumer', term=target), term=target)
            yield from walk(self.roots[1], None, [], 'consumer_definition')
            yield from walk(self.roots[0], target, [], 'source_consumer_obligation')

        for question, origin in proposals():
            if digest(question) not in self.tried:
                return question, dict(origin, E_version=self.version,
                                      checked_separator=self.live_checkpoint)
        return None

    def add(self, value):
        if value is None:
            return False
        fact, pair = value
        a, b = pair
        if a == b or pair in self.pairs:
            self.audit.counts['duplicate_or_reflexive_facts'] += 1
            return False
        invalidated = self.live_checkpoint
        self.live_model = self.live_checkpoint = None
        self.facts.append(fact)
        self.equations.append(pair)
        self.pairs.add(pair)
        self.replacements[a] = b
        self.version += 1
        self.audit.counts['emitted_native_facts'] += 1
        self.audit.decisions.append(dict(event='extend_E', version=self.version,
                                         equation=list(pair), invalidated_separator=invalidated))
        if invalidated is not None:
            self.audit.counts['invalidated_separators'] += 1
        return True

    def export(self):
        return self.graph.finish(self.equations, self.roots, self.facts)
