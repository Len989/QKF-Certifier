"""One admitted immutable source scope; compile each distinct consumer once."""
from dataclasses import dataclass
from types import MappingProxyType
from research.source_lemmas.context import (
    requests, target_context, scope, LIMIT, source_text, target_domain, Unsupported,
    canonical, require)
from research.source_query.context import prepare as prepare_first
from research.signed_predicates.frontend import target_value
from research.source_lemmas.terms import roots
from .values import Capability, _KEY, own, plain


@dataclass(frozen=True, slots=True, init=False)
class Context(Capability):
    request: object
    selection: object
    ir: object
    spec: object
    guards: object
    width: object
    limit: int
    domain: tuple
    domain_edges: int
    claim: tuple
    key: str
    _binding: object

    def guard(self, count, sign):
        return all(target_value(g, count, sign) for g in self.guards)

    def binding(self):
        return plain(self._binding)


@dataclass(frozen=True, slots=True, init=False)
class Admission(Capability):
    contexts: object
    requests: tuple
    scope: object
    scope_key: str

    def target(self, raw):
        # External dictionaries are validated/canonicalized, never taken as tokens.
        key = canonical(raw)
        require(key in self.contexts, 'request outside this admitted build')
        return self.contexts[key]


def admit(source, batch):
    source = source_text(source)
    items = requests(batch)
    anchor = prepare_first(source, items[0])
    if anchor.limit > LIMIT:
        raise Unsupported('lemma native algebra supports guard/target counts 0..3')
    anchor.limit = LIMIT
    states, anchor.domain_edges = target_domain(LIMIT, anchor.width)
    anchor.domain = tuple(s for s in states if anchor.guard(*s))
    shared = dict(selection=own(anchor.selection), ir=own(anchor.ir),
                  guards=own(anchor.guards), width=anchor.width, limit=LIMIT,
                  domain=anchor.domain, domain_edges=anchor.domain_edges)
    contexts = {}
    for request in items:
        key = canonical(request)
        if key not in contexts:
            ctx = target_context(anchor, request)
            contexts[key] = Context(_KEY, **shared, request=own(ctx.request), spec=own(ctx.spec),
                claim=own(roots(ctx)), key=key, _binding=own(ctx.binding()))
    admitted_scope = scope(anchor)
    return Admission(_KEY, contexts=MappingProxyType(contexts), requests=own(items),
                     scope=own(admitted_scope), scope_key=canonical(admitted_scope))
