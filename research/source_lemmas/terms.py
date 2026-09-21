"""Closed semantic terms cross presentations; graph node numbers never do."""
from research.source_query.encoding import Graph
from research.source_query.rules import check_fact
from research.ground_query.schema import fields, require
from .context import digest, scope, snapshot, freeze


def term(graph, index, memo=None):
    memo = {} if memo is None else memo
    if index not in memo:
        op, args = graph.row(index)
        memo[index] = [op, *(term(graph, a, memo) for a in args)]
    return memo[index]


def intern(graph, value, depth=0):
    require(depth <= 128 and type(value) is list and value
            and type(value[0]) is str and value[0] in graph.signature, 'closed native term')
    op, args = value[0], value[1:]
    desc = graph.signature[op]
    require(len(args) == len(desc['args']), 'native term arity')
    children = [intern(graph, a, depth + 1) for a in args]
    require(all(graph.signature[graph.row(i)[0]]['result'] == sort
                for i, sort in zip(children, desc['args'])), 'native term sorts')
    return graph.node(op, *children)


def pair(graph, value):
    require(type(value) is list and len(value) == 2, 'closed equality')
    a, b = (intern(graph, t) for t in value)
    require(graph.signature[graph.row(a)[0]]['result'] ==
            graph.signature[graph.row(b)[0]]['result'], 'equality sorts')
    return a, b


def ground(ctx, premises, claim):
    g = Graph(ctx)
    equations = [pair(g, p) for p in premises]
    return g.finish(equations, pair(g, claim), [])[0]


def roots(ctx):
    g = Graph(ctx)
    return [term(g, g.source()), term(g, g.target())]


def native_entry(ctx, graph, fact, endpoints):
    evidence = dict(fact)
    if 'term' in evidence:
        evidence['term'] = term(graph, evidence['term'])
    body = dict(scope=scope(ctx), claim=[term(graph, t) for t in endpoints], evidence=evidence)
    return dict(id=digest(body), **body)


def check_native(ctx, raw):
    entry = snapshot(raw)
    fields(entry, ('id', 'scope', 'claim', 'evidence'), 'native E entry')
    body = {k: v for k, v in entry.items() if k != 'id'}
    require(freeze(entry['scope']) == freeze(scope(ctx)) and entry['id'] == digest(body), 'native scope/identity')
    g = Graph(ctx)
    expected = pair(g, entry['claim'])
    evidence = snapshot(entry['evidence'])
    require(type(evidence) is dict, 'native evidence')
    if 'term' in evidence:
        evidence['term'] = intern(g, evidence['term'])
    require(check_fact(ctx, g, evidence) == expected, 'native E claim differs from checked evidence')
    return entry
