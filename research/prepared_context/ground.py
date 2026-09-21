"""Admit a typed ground DAG once; search and proof replay share that input."""
from dataclasses import dataclass
from research.ground_query.schema import parse, require, INPUT_SCHEMA
from research.source_query.encoding import MAX_TERMS
from .values import Capability, _KEY, own, plain


@dataclass(frozen=True, slots=True, init=False)
class Parsed(Capability):
    sorts: tuple
    signature: object
    nodes: tuple
    node_sorts: tuple
    depths: tuple
    equations: tuple
    queries: tuple
    horizon: int
    identity: str
    _request: object

    def request(self):
        return plain(self._request)


def admit(request):
    inp = parse(request)
    # The legacy Input's nested signature is mutable: own it before issuance.
    values = {name: getattr(inp, name) for name in
              ('sorts', 'nodes', 'node_sorts', 'depths', 'equations', 'queries', 'horizon', 'identity')}
    return Parsed(_KEY, **values, signature=own(inp.signature), _request=own(request))


def input_of(prepared):
    require(type(prepared) is Parsed, 'admitted ground capability required')
    return prepared


def compile_terms(signature, equations, claim):
    """Closed terms were checked on insertion; final typed DAG is admitted once.

    Preserve the old first-occurrence topological order and exact Sub(E)∪Sub(O).
    No graph IDs or mutable term dictionaries cross the capability boundary.
    """
    nodes, lookup = [], {}
    def emit(term):
        if term not in lookup:
            args = [emit(child) for child in term[1:]]
            require(len(nodes) < MAX_TERMS, 'source ground-term budget')
            lookup[term] = len(nodes)
            nodes.append(dict(op=term[0], args=args))
        return lookup[term]
    pairs = [[emit(a), emit(b)] for a, b in equations]
    query = [[emit(a), emit(b)] for a, b in [claim]]
    return admit(dict(schema=INPUT_SCHEMA, sorts=['Word', 'Bool'], signature=plain(signature),
                      nodes=nodes, equations=pairs, queries=query))
