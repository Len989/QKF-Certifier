"""Immutable E/E+ prefixes and locally checked obligations; no search imports.

There is intentionally no trusted loader. External packets go to the unchanged
research.source_lemmas.checker; local promotion requires an exact capability.
"""
from dataclasses import dataclass
from research.ground_query.schema import fields, require
from research.source_lemmas.context import snapshot, digest, integer, canonical, PAYLOAD
from research.source_lemmas.terms import pair, intern, term
from research.source_query.encoding import Graph
from research.source_query.rules import check_fact
from .context import admit, Context
from .ground import compile_terms
from .ground_check import check as check_ground
from .values import Capability, _KEY, own, plain


@dataclass(frozen=True, slots=True, init=False)
class Obligation(Capability):
    _owner: object
    _ctx: Context
    basis: object
    epoch: object
    via: object
    ground: object
    binding: str


@dataclass(frozen=True, slots=True, init=False)
class CheckedGoal(Capability):
    _owner: object
    _ctx: Context
    _item: object
    _result: object
    _obligation: object

    def result(self):
        return plain(self._result)


@dataclass(frozen=True, slots=True, init=False)
class Presentation(Capability):
    _admission: object
    _E: tuple
    _plus: tuple

    def context(self):
        return next(iter(self._admission.contexts.values()))

    def target(self, request):
        return self._admission.target(request)

    def scope(self):
        return plain(self._admission.scope)

    def native(self):
        return [plain(row) for row in self._E]

    def lemmas(self):
        return [plain(row) for row in self._plus]

    def epoch(self):
        return dict(native=len(self._E), lemmas=len(self._plus))

    def _replace(self, *, native=None, lemmas=None):
        return Presentation(_KEY, _admission=self._admission,
            _E=self._E if native is None else native, _plus=self._plus if lemmas is None else lemmas)

    def add_native(self, raw):
        require(len(self._E) < 4096, 'native presentation budget')
        entry = snapshot(raw)
        fields(entry, ('id', 'scope', 'claim', 'evidence'), 'native E entry')
        body = {k: v for k, v in entry.items() if k != 'id'}
        require(canonical(entry['scope']) == self._admission.scope_key and entry['id'] == digest(body),
                'native scope/identity')
        require(entry['id'] not in {r['id'] for r in self._E}, 'duplicate native identity')
        ctx = self.context()
        graph = Graph(ctx)
        expected = pair(graph, entry['claim'])
        evidence = snapshot(entry['evidence'])
        require(type(evidence) is dict, 'native evidence')
        if 'term' in evidence:
            evidence['term'] = intern(graph, evidence['term'])
        require(check_fact(ctx, graph, evidence) == expected, 'native E claim differs from checked evidence')
        return self._replace(native=(*self._E, own(entry)))

    def premises(self, basis, epoch):
        fields(basis, ('native', 'lemmas'), 'proof basis')
        fields(epoch, ('native', 'lemmas'), 'presentation epoch')
        n = integer(epoch['native'], 0, len(self._E), 'native prefix')
        l = integer(epoch['lemmas'], 0, len(self._plus), 'lemma prefix')
        require(all(r['native_count'] <= n for r in self._plus[:l]), 'epoch precedes lemma foundations')
        pairs = []
        for kind, rows in (('native', self._E[:n]), ('lemmas', self._plus[:l])):
            ids = basis[kind]
            require(type(ids) is list and len(ids) <= 4096 and all(type(i) is str for i in ids)
                    and len(ids) == len(set(ids)), 'unique premise IDs')
            available = {r['id']: r for r in rows}
            require(all(i in available for i in ids), 'missing, forward or foreign premise')
            pairs.extend(available[i]['claim'] for i in ids)
        return pairs

    def prepare(self, ctx, basis, epoch=None, via=None):
        require(type(ctx) is Context and self._admission.contexts.get(ctx.key) is ctx,
                'foreign admitted consumer')
        epoch = self.epoch() if epoch is None else snapshot(epoch)
        basis = snapshot(basis)
        premises = self.premises(basis, epoch)
        claim = ctx.claim
        if via is not None:
            require(type(via) is str, 'prior lemma identity')
            prior = [r for r in self._plus[:epoch['lemmas']] if r['id'] == via]
            require(len(prior) == 1 and prior[0]['claim'][0] == claim[0],
                    'prior lemma must prove this exact left endpoint')
            claim = (prior[0]['claim'][1], claim[1])
        ground = compile_terms(self._admission.scope['native_algebra'], premises, claim)
        return Obligation(_KEY, _owner=self, _ctx=ctx, basis=own(basis), epoch=own(epoch),
                          via=via, ground=ground, binding=canonical(dict(basis=basis, epoch=epoch, via=via)))

    def promote(self, checked):
        require(type(checked) is CheckedGoal and checked._owner is self,
                'promotion needs a checked goal from this exact previous presentation')
        item = plain(checked._item)
        require(item['kind'] == 'ground' and checked._result['status'] == 'certified',
                'promotion needs a positive ground derivation')
        require(item['epoch'] == self.epoch(), 'promotion of stale presentation')
        body = dict(scope=self.scope(), claim=plain(checked._ctx.claim),
                    native_count=item['epoch']['native'], prior_lemmas=item['epoch']['lemmas'],
                    basis=item['basis'], via_lemma=item['via_lemma'], certificate=item['certificate'])
        lemma = dict(id=digest(body), **body)
        require(len(self._plus) < 64 and lemma['id'] not in {r['id'] for r in self._plus},
                'lemma identity/storage')
        return self._replace(lemmas=(*self._plus, own(lemma))), lemma

    def model_for(self, obligation, checked):
        require(type(obligation) is Obligation and obligation._owner is self
                and plain(obligation.epoch) == self.epoch(), 'stale or foreign model scope')
        require(type(checked) is CheckedGoal and checked._owner is self
                and checked._obligation is obligation, 'model belongs to another exact obligation')
        require(checked._result['status'] == 'unresolved' and checked._item['kind'] == 'ground',
                'checked separating model required')
        core = checked._item['certificate']
        return plain(core['models'][core['goals'][0]['model']])

    def verify(self, raw_request, raw_item, *, prepared=None):
        ctx = self.target(raw_request)
        item = snapshot(raw_item)
        require(type(item) is dict and type(item.get('kind')) is str, 'consumer obligation')
        kind = item['kind']
        base = dict(schema='qkf-source-lemma-result-v1', width=plain(ctx.request['width']), guards=plain(ctx.guards),
                    lean_checked=False, source_refutation=False,
                    scope='retained guarded modular semantics; closed ground facts and Python checkers')
        if kind == 'empty':
            fields(item, ('kind',), 'empty-domain obligation')
            require(not ctx.domain, 'guard domain is not empty')
            result = dict(base, status='verified_empty_domain', reason='empty_guard', target_checked=False)
        elif kind == 'witness':
            fields(item, ('kind', 'certificate'), 'concrete source violation')
            from research.source_query.checker import witness
            from research.source_query.context import PROOF
            proof = item['certificate']
            fields(proof, ('schema', 'binding', 'kind', 'evidence'), 'concrete source proof')
            require(ctx.domain and proof['schema'] == PROOF and proof['kind'] == 'witness'
                    and proof['binding'] == ctx.binding(), 'concrete witness source/guard/width binding')
            result = dict(base, status='refuted', reason='concrete_violation', target_checked=True,
                          all_positive_widths=False, source_refutation=True, witness=witness(ctx, proof['evidence']))
        elif kind == 'lemma':
            fields(item, ('kind', 'lemma'), 'proved consumer lemma')
            require(ctx.domain and type(item['lemma']) is str, 'nonempty checked lemma goal')
            found = [r for r in self._plus if r['id'] == item['lemma']]
            require(len(found) == 1 and found[0]['claim'] == ctx.claim, 'lemma does not prove this independent consumer')
            result = dict(base, status='certified', reason='consumer_closed', target_checked=True,
                          all_positive_widths=ctx.width is None, active_native_axioms=0, active_lemma_axioms=1)
        else:
            require(kind in ('ground', 'inactive'), 'unknown consumer proof kind')
            fields(item, ('kind', 'basis', 'epoch', 'via_lemma', 'certificate' if kind == 'ground' else 'horizon'), 'ground obligation')
            require(ctx.domain, 'empty guard needs explicit empty obligation')
            if prepared is None:
                prepared = self.prepare(ctx, item['basis'], item['epoch'], item['via_lemma'])
            require(type(prepared) is Obligation and prepared._owner is self and prepared._ctx is ctx
                    and prepared.binding == canonical(dict(basis=item['basis'], epoch=item['epoch'],
                                                           via=item['via_lemma'])), 'prepared obligation binding')
            inp = prepared.ground
            if kind == 'inactive':
                h = integer(item['horizon'], 0, inp.horizon, 'inactive horizon')
                required = max(inp.depths[x] for p in inp.queries for x in p)
                require(h < required, 'query is already active')
                result = dict(base, status='unresolved', reason='insufficient_horizon', target_checked=False,
                              ground_relation='inactive_query', horizon=h, required_horizon=required,
                              final_horizon=inp.horizon, via_lemma=item['via_lemma'])
            else:
                verified = check_ground(inp, item['certificate'])
                require(verified['mode'] == 'entailment', 'consumer needs entailment')
                relation = verified['goals'][0]['status']
                equal = relation == 'equal'
                result = dict(base, status='certified' if equal else 'unresolved', target_checked=equal,
                    reason='consumer_closed' if equal else 'insufficient_horizon' if relation == 'not_visible'
                    else 'not_entailed_from_current_presentation', ground_relation=relation,
                    all_positive_widths=equal and ctx.width is None,
                    active_native_axioms=len(item['basis']['native']), active_lemma_axioms=len(item['basis']['lemmas']),
                    via_lemma=item['via_lemma'],
                    ground_obligation='lemma_rhs_equals_consumer' if item['via_lemma'] else 'source_equals_consumer',
                    ground_result=verified)
        return CheckedGoal(_KEY, _owner=self, _ctx=ctx, _item=own(item), _result=own(result),
                           _obligation=prepared)

    def payload(self, items):
        return dict(schema=PAYLOAD, scope=self.scope(), E=self.native(), E_plus=self.lemmas(), items=items)


def native_entry(presentation, graph, fact, endpoints):
    evidence = dict(fact)
    if 'term' in evidence:
        evidence['term'] = term(graph, evidence['term'])
    body = dict(scope=presentation.scope(), claim=[term(graph, t) for t in endpoints], evidence=evidence)
    return dict(id=digest(body), **body)


def open_context(source, batch):
    admission = admit(source, batch)
    return Presentation(_KEY, _admission=admission, _E=(), _plus=()), plain(admission.requests)
