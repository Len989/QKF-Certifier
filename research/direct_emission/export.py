"""Incremental direct DAG assembly from process-local PR48 capabilities.

This module issues no consumer capability. The unchanged public cold checker
must replay the final serialized envelope, including every retained foundation.
"""
from dataclasses import dataclass
from research.ground_query.schema import INPUT_SCHEMA, digest as ground_digest
from research.source_lemmas.context import canonical, digest, require
from research.prepared_context.checker import Presentation, CheckedGoal
from research.prepared_context.values import Capability, _KEY, own, plain
from research.applicable_summary.direct import SCHEMA, event_closure


@dataclass(frozen=True, slots=True, init=False)
class Emission(Capability):
    evidence: object


def slice_checked(checked):
    """Slice the already admitted DAG; never reconstruct or parse its request.

    First-occurrence term order and chronological event order match PR45.
    Reflexive queries declare auxiliary congruence syntax, never extra axioms.
    """
    require(type(checked) is CheckedGoal and checked._item['kind'] == 'ground'
            and checked._result['status'] == 'certified', 'checked positive ground goal required')
    obligation = checked._obligation
    require(obligation is not None and obligation._owner is checked._owner
            and obligation._ctx is checked._ctx, 'checked input ownership')
    return _slice_ground(obligation.ground, plain(checked._item['certificate']))


def _slice_ground(inp, proof):
    """Mechanical renaming only; production enters through slice_checked."""
    keep = event_closure(proof)
    axioms = sorted({proof['events'][i]['equation'] for i in keep
                     if proof['events'][i]['rule'] == 'axiom'})
    nodes, depths, names = [], [], {}

    def rename(old):
        if old not in names:
            op, children = inp.nodes[old]
            args = [rename(a) for a in children]
            names[old] = len(nodes)
            nodes.append(dict(op=op, args=args))
            depths.append(inp.depths[old])
        return names[old]

    equations = [[rename(a), rename(b)] for a, b in (inp.equations[i] for i in axioms)]
    query = [rename(a) for a in inp.queries[0]]
    event_map = {old: new for new, old in enumerate(keep)}
    equation_map = {old: new for new, old in enumerate(axioms)}
    events = []
    for i in keep:
        e = proof['events'][i]
        e['left'], e['right'] = rename(e['left']), rename(e['right'])
        if e['rule'] == 'axiom':
            e['equation'] = equation_map[e['equation']]
        else:
            e['premises'] = [[event_map[j] for j in path] for path in e['premises']]
        events.append(e)
    reachable, pending = set(), [i for pair in [*equations, query] for i in pair]
    while pending:
        i = pending.pop()
        if i not in reachable:
            reachable.add(i)
            pending.extend(nodes[i]['args'])
    extra = set(range(len(nodes))) - reachable
    support = sorted(extra - {a for i in extra for a in nodes[i]['args']})
    request = dict(schema=INPUT_SCHEMA, sorts=list(inp.sorts), signature=plain(inp.signature),
                   nodes=nodes, equations=equations, queries=[query, *[[i, i] for i in support]])
    goal = proof['goals'][0]
    goal['path'] = [event_map[i] for i in goal['path']]
    require(goal['lower_model'] is None, 'entailment export, not threshold minimization')
    cert = dict(schema=proof['schema'], request_sha256=ground_digest(request), mode='entailment',
                horizon=goal['depth'], events=events, models=[], goals=[goal, *[
                    dict(status='equal', path=[], depth=depths[i], lower_model=None) for i in support]])
    return request, cert, axioms


class Assembler:
    def __init__(self, presentation):
        require(type(presentation) is Presentation and not presentation._E and not presentation._plus,
                'assembler starts with a fresh admitted presentation')
        self.current = presentation
        self.nodes, self.dependencies, self.goals = {}, {}, []

    def _emit(self, body):
        identity = digest(body)
        if identity not in self.nodes:
            self.nodes[identity] = own(dict(id=identity, **body))
        return identity

    def native(self, presentation):
        old = self.current
        require(type(presentation) is Presentation and presentation._admission is old._admission
                and presentation._plus is old._plus and len(presentation._E) == len(old._E) + 1
                and all(a is b for a, b in zip(old._E, presentation._E)), 'next checked native prefix')
        entry = plain(presentation._E[-1])
        self.dependencies[entry['id']] = self._emit(dict(kind='native', entry=entry))
        self.current = presentation

    def _checked(self, checked):
        require(type(checked) is CheckedGoal and checked._owner is self.current,
                'checked conclusion from the exact current presentation required')

    def equality(self, checked):
        self._checked(checked)
        request, proof, selected = slice_checked(checked)
        item = checked._item
        ids = (*item['basis']['native'], *item['basis']['lemmas'])
        parents = [self.dependencies[ids[i]] for i in selected]
        via = None if item['via_lemma'] is None else self.dependencies[item['via_lemma']]
        return self._emit(dict(kind='equality', claim=plain(checked._ctx.claim), premises=parents,
                               via=via, request=request, proof=proof))

    def promote(self, checked, presentation):
        self._checked(checked)
        old, item = self.current, checked._item
        require(type(presentation) is Presentation and presentation._admission is old._admission
                and presentation._E is old._E and len(presentation._plus) == len(old._plus) + 1
                and all(a is b for a, b in zip(old._plus, presentation._plus)), 'next checked lemma prefix')
        require(item['kind'] == 'ground' and plain(item['epoch']) == old.epoch(), 'current ground promotion')
        lemma = presentation._plus[-1]
        expected = dict(scope=old.scope(), claim=plain(checked._ctx.claim),
                        native_count=len(old._E), prior_lemmas=len(old._plus),
                        basis=plain(item['basis']), via_lemma=item['via_lemma'], certificate=plain(item['certificate']))
        require(canonical(plain(lemma)) == canonical(dict(id=digest(expected), **expected)),
                'lemma must import this exact checked derivation')
        self.dependencies[lemma['id']] = self.equality(checked)
        self.current = presentation

    def goal(self, checked):
        self._checked(checked)
        item = checked._item
        if checked._result['status'] == 'unresolved':
            goal = None  # The complete scoped native presentation is retained by the fallback.
        elif item['kind'] == 'ground':
            goal = dict(kind='node', node=self.equality(checked))
        elif item['kind'] == 'lemma':
            goal = dict(kind='node', node=self.dependencies[item['lemma']])
        else:
            require(item['kind'] in ('empty', 'witness'), 'direct terminal obligation')
            goal = plain(item)
        self.goals.append(own(goal))

    def cached(self, previous):
        require(type(previous) is int and 0 <= previous < len(self.goals)
                and self.goals[previous] is not None, 'earlier terminal goal')
        self.goals.append(own(dict(kind='cached', previous=previous)))

    def finish(self):
        require(all(g is not None for g in self.goals), 'scoped model requires native fallback')
        # Dependency-first DFS preserves PR45 wire order while excluding nodes
        # unused by any final goal. This is reachability, not DAG minimization.
        order, seen = [], set()
        def visit(identity):
            if identity in seen:
                return
            node = self.nodes[identity]
            if node['kind'] == 'equality':
                for parent in node['premises']:
                    visit(parent)
                if node['via'] is not None:
                    visit(node['via'])
            seen.add(identity)
            order.append(node)
        for goal in self.goals:
            if goal['kind'] == 'node':
                visit(goal['node'])
        evidence = own(dict(schema=SCHEMA, scope=self.current.scope(),
                            nodes=[plain(n) for n in order], goals=[plain(g) for g in self.goals]))
        return Emission(_KEY, evidence=evidence)

    def accounting(self, emission=None):
        retained = () if emission is None else emission.evidence['nodes']
        return dict(native_available=len(self.current._E), lemmas_available=len(self.current._plus),
                    nodes_created=len(self.nodes), dependencies=len(retained),
                    native_retained=sum(n['kind'] == 'native' for n in retained),
                    emitted_events=sum(len(n['proof']['events']) for n in self.nodes.values() if n['kind'] == 'equality'),
                    retained_events=sum(len(n['proof']['events']) for n in retained if n['kind'] == 'equality'),
                    auxiliary_reflexive_queries=sum(len(n['request']['queries']) - 1 for n in retained if n['kind'] == 'equality'))
