"""Checked E/E+ capabilities and cold portable replay; no search imports."""
from dataclasses import dataclass
from research.ground_query.schema import fields, parse, require
from research.ground_query.checker import check as check_ground
from research.signed_compact import dag
from .context import (prepare, target_context, scope, context_json, from_context_json,
                      snapshot, digest, integer, freeze, thaw, PAYLOAD)
from .terms import check_native, ground, roots

_KEY = object()


@dataclass(frozen=True, slots=True, init=False)
class CheckedGoal:
    """Ordinary-API capability; a JSON receipt cannot be promoted."""
    _owner: tuple
    _request: str
    _item: str
    _result: str

    def __init__(self, key=None, **values):
        require(key is _KEY, 'check the actual goal before promoting a lemma')
        for name in self.__slots__:
            object.__setattr__(self, name, values[name])

    def result(self):
        return thaw(self._result)

    def __reduce_ex__(self, protocol):
        raise TypeError('export foundations and check again; do not pickle a checked goal')


@dataclass(frozen=True, slots=True, init=False)
class CheckedPresentation:
    """Immutable source-bound context. No security claim against Python reflection."""
    _ctx: str
    _E: str
    _plus: str

    def __init__(self, key=None, **values):
        require(key is _KEY, 'load the source and proofs; a receipt is not a presentation')
        for name in self.__slots__:
            object.__setattr__(self, name, values[name])

    def __reduce_ex__(self, protocol):
        raise TypeError('checked presentations are process-local; export and recheck')

    def context(self):
        return from_context_json(self._ctx)

    def native(self):
        return thaw(self._E)

    def lemmas(self):
        return thaw(self._plus)

    def epoch(self):
        return dict(native=len(self.native()), lemmas=len(self.lemmas()))

    def owner(self):
        return self._ctx, self._E, self._plus

    def _replace(self, native=None, lemmas=None):
        return CheckedPresentation(_KEY, _ctx=self._ctx,
            _E=self._E if native is None else freeze(native),
            _plus=self._plus if lemmas is None else freeze(lemmas))

    def add_native(self, raw):
        rows = self.native()
        require(len(rows) < 4096, 'native presentation budget')
        entry = check_native(self.context(), raw)
        require(entry['id'] not in {r['id'] for r in rows}, 'duplicate native identity')
        return self._replace(native=[*rows, entry])

    def premises(self, basis, epoch):
        fields(basis, ('native', 'lemmas'), 'proof basis')
        fields(epoch, ('native', 'lemmas'), 'presentation epoch')
        natives, lemmas = self.native(), self.lemmas()
        n = integer(epoch['native'], 0, len(natives), 'native prefix')
        l = integer(epoch['lemmas'], 0, len(lemmas), 'lemma prefix')
        require(all(row['native_count'] <= n for row in lemmas[:l]), 'epoch precedes lemma foundations')
        pairs = []
        for kind, rows in (('native', natives[:n]), ('lemmas', lemmas[:l])):
            ids = basis[kind]
            require(type(ids) is list and len(ids) <= 4096
                    and all(type(i) is str for i in ids) and len(ids) == len(set(ids)), 'unique premise IDs')
            available = {r['id']: r for r in rows}
            require(all(i in available for i in ids), 'missing, forward or foreign premise')
            pairs.extend(available[i]['claim'] for i in ids)
        return pairs

    def request(self, claim, basis, epoch):
        return ground(self.context(), self.premises(basis, epoch), claim)

    def residual_claim(self, claim, via, epoch):
        """Checked transitivity: source=L.rhs, then prove L.rhs=consumer."""
        require(type(claim) is list and len(claim) == 2, 'closed lemma/consumer equality')
        # Validate the entire epoch even when the residual has no axiom premises.
        self.premises(dict(native=[], lemmas=[]), epoch)
        if via is None:
            return claim
        require(type(via) is str, 'prior lemma identity')
        prior = [r for r in self.lemmas()[:epoch['lemmas']] if r['id'] == via]
        require(len(prior) == 1 and prior[0]['claim'][0] == claim[0],
                'prior lemma must prove this exact left endpoint')
        return [prior[0]['claim'][1], claim[1]]

    def add_lemma(self, raw):
        lemma = snapshot(raw)
        fields(lemma, ('id', 'scope', 'claim', 'native_count', 'prior_lemmas', 'basis', 'via_lemma', 'certificate'),
               'derived E+ lemma')
        body = {k: v for k, v in lemma.items() if k != 'id'}
        require(freeze(lemma['scope']) == freeze(scope(self.context())) and lemma['id'] == digest(body), 'lemma scope/identity')
        rows = self.lemmas()
        require(len(rows) < 64 and lemma['id'] not in {r['id'] for r in rows}, 'lemma identity/storage')
        integer(lemma['native_count'], 0, len(self.native()), 'lemma native prefix')
        integer(lemma['prior_lemmas'], 0, len(rows), 'lemma prior prefix')
        require(lemma['native_count'] == len(self.native()) and lemma['prior_lemmas'] == len(rows),
                'lemma must be checked in exactly the preceding presentation')
        epoch = dict(native=lemma['native_count'], lemmas=lemma['prior_lemmas'])
        claim = self.residual_claim(lemma['claim'], lemma['via_lemma'], epoch)
        result = check_ground(self.request(claim, lemma['basis'], epoch), lemma['certificate'])
        require(result['mode'] == 'entailment' and result['goals'][0]['status'] == 'equal',
                'only a proved equality can enter E+')
        return self._replace(lemmas=[*rows, lemma])

    def promote(self, checked):
        require(type(checked) is CheckedGoal and checked._owner == self.owner(),
                'promotion needs a checked goal from this exact previous presentation')
        item = thaw(checked._item)
        require(item['kind'] == 'ground' and checked.result()['status'] == 'certified',
                'promotion needs a positive ground derivation')
        require(item['epoch'] == self.epoch(), 'promotion of stale presentation')
        ctx = target_context(self.context(), thaw(checked._request))
        body = dict(scope=scope(ctx), claim=roots(ctx), native_count=item['epoch']['native'],
                    prior_lemmas=item['epoch']['lemmas'], basis=item['basis'],
                    via_lemma=item['via_lemma'], certificate=item['certificate'])
        lemma = dict(id=digest(body), **body)
        rows = self.lemmas()
        require(len(rows) < 64 and lemma['id'] not in {r['id'] for r in rows}, 'lemma identity/storage')
        # The capability contains the exact already-checked proof and previous E/E+.
        # Cold load uses add_lemma and replays that proof instead of trusting this object.
        return self._replace(lemmas=[*rows, lemma]), lemma

    def verify(self, raw_request, raw_item):
        ctx = target_context(self.context(), raw_request)
        item = snapshot(raw_item)
        require(type(item) is dict and type(item.get('kind')) is str, 'consumer obligation')
        kind = item['kind']
        base = dict(schema='qkf-source-lemma-result-v1', width=ctx.request['width'], guards=ctx.guards,
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
            found = [r for r in self.lemmas() if r['id'] == item['lemma']]
            require(len(found) == 1 and found[0]['claim'] == roots(ctx), 'lemma does not prove this independent consumer')
            result = dict(base, status='certified', reason='consumer_closed', target_checked=True,
                          all_positive_widths=ctx.width is None, active_native_axioms=0, active_lemma_axioms=1)
        else:
            require(kind in ('ground', 'inactive'), 'unknown consumer proof kind')
            fields(item, ('kind', 'basis', 'epoch', 'via_lemma', 'certificate' if kind == 'ground' else 'horizon'), 'ground obligation')
            require(ctx.domain, 'empty guard needs explicit empty obligation')
            claim = self.residual_claim(roots(ctx), item['via_lemma'], item['epoch'])
            request = self.request(claim, item['basis'], item['epoch'])
            inp = parse(request)
            if kind == 'inactive':
                h = integer(item['horizon'], 0, inp.horizon, 'inactive horizon')
                required = max(inp.depths[x] for p in inp.queries for x in p)
                require(h < required, 'query is already active')
                result = dict(base, status='unresolved', reason='insufficient_horizon', target_checked=False,
                              ground_relation='inactive_query', horizon=h, required_horizon=required,
                              final_horizon=inp.horizon, via_lemma=item['via_lemma'])
            else:
                verified = check_ground(request, item['certificate'])
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
        return CheckedGoal(_KEY, _owner=self.owner(), _request=freeze(ctx.request),
                           _item=freeze(item), _result=freeze(result))

    def payload(self, items):
        return dict(schema=PAYLOAD, scope=scope(self.context()), E=self.native(), E_plus=self.lemmas(), items=items)


def open_context(source, batch):
    ctx, items = prepare(source, batch)
    return CheckedPresentation(_KEY, _ctx=context_json(ctx), _E='[]', _plus='[]'), items


def load_presentation(source, batch, foundations):
    context, requests = open_context(source, batch)
    foundations = snapshot(foundations)
    fields(foundations, ('scope', 'E', 'E_plus'), 'portable foundations')
    require(freeze(foundations['scope']) == freeze(scope(context.context())), 'source-bound packet scope')
    natives, lemmas = foundations['E'], foundations['E_plus']
    require(type(natives) is list and len(natives) <= 4096 and type(lemmas) is list and len(lemmas) <= 64,
            'presentation storage budget')
    cursor = 0
    for lemma in lemmas:
        require(type(lemma) is dict, 'lemma record')
        stop = integer(lemma.get('native_count'), cursor, len(natives), 'chronological native prefix')
        while cursor < stop:
            context = context.add_native(natives[cursor])
            cursor += 1
        context = context.add_lemma(lemma)
    for native in natives[cursor:]:
        context = context.add_native(native)
    return context, requests


def load(source, batch, packet):
    payload = dag.unpack(packet)
    fields(payload, ('schema', 'scope', 'E', 'E_plus', 'items'), 'portable lemma presentation')
    require(payload['schema'] == PAYLOAD, 'lemma packet schema')
    context, requests = load_presentation(source, batch, {k: payload[k] for k in ('scope', 'E', 'E_plus')})
    items = payload['items']
    require(type(items) is list and len(items) == len(requests), 'complete independent goal list')
    results = []
    for i, (request, item) in enumerate(zip(requests, items)):
        require(type(item) is dict, 'consumer item')
        if item.get('kind') == 'cached_goal':
            fields(item, ('kind', 'previous'), 'exact goal cache')
            j = integer(item['previous'], 0, i - 1, 'strictly earlier checked goal')
            require(freeze(request) == freeze(requests[j]), 'ordinary cache requires the exact independent request')
            require(results[j]['status'] in ('certified', 'refuted', 'verified_empty_domain'),
                    'a scoped lower model cannot be cached as a source verdict')
            result = snapshot(results[j])
        else:
            result = context.verify(request, item).result()
        results.append(result)
    return context, results


def check(source, batch, packet):
    return load(source, batch, packet)[1]
