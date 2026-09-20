"""Non-interchangeable checked evidence. A finite value or separator is not a theorem of a program."""
from dataclasses import dataclass
from .contract import canonical, snapshot, digest, need, request

_KEY = object()


@dataclass(frozen=True, init=False)
class Evidence:
    kind: str
    _payload: str

    def __init__(self, key=None, *, kind=None, payload=None):
        need(key is _KEY, 'evidence requires independent validation')
        object.__setattr__(self, 'kind', kind)
        object.__setattr__(self, '_payload', canonical(payload))

    def data(self):
        return snapshot(__import__('json').loads(self._payload))

    def __reduce_ex__(self, protocol):
        raise TypeError('recheck external evidence; no trusted pickle receipt')


class NativeFact(Evidence):
    """One checked source value at one exact word, NOT an all-width law."""


class AbstractSeparator(Evidence):
    """Model of the specified finite theory/horizon, NOT a program execution."""


class ConcreteWitness(Evidence):
    """An independently recomputed source/target mismatch at its final width."""


class Unresolved(Evidence):
    """An outstanding obligation; can never authorize a positive verdict."""


def native_fact(raw_request, raw, width, claimed_value):
    r = request(raw_request)
    need(not r['conditions'], 'conditional native facts not supported yet')
    from research.signed_bridge.model import read
    from research.signed_predicates.semantics import evaluate
    ir = read(r['source'], r['selection'])
    actual = evaluate(ir, raw, width)
    need(type(claimed_value) is bool and actual == claimed_value, 'native point value mismatch')
    return NativeFact(_KEY, kind='native_fact', payload={
        'request_sha256': digest(r), 'raw': raw, 'width': width, 'value': actual,
        'scope': 'one exact modular word only', 'all_positive_widths': False,
        'target_checked': False, 'native_execution_checked': False})


def abstract_separator(presentation, certificate, left, right, horizon):
    from research.pure_rows.checker import explain
    result = explain(presentation, certificate, left, right, horizon)
    need(result['relation'] == 'not_forced_equal', 'model does not separate the requested pair')
    return AbstractSeparator(_KEY, kind='abstract_separator', payload={
        'query': result, 'source_refutation': False, 'scope': 'specified finite presentation and horizon'})


def concrete_witness(raw_request, certificate):
    r = request(raw_request)
    need(not r['conditions'], 'conditional witness checking not supported yet')
    from research.signed_witness.checker import check
    result = check(r['source'], r['consumer']['target'], certificate)
    need(result['status'] == 'refuted', 'verified mismatch required')
    return ConcreteWitness(_KEY, kind='concrete_witness', payload=result)


def unresolved(code, detail):
    need(code in {'unsupported_conditions', 'unsupported', 'budget_exhausted',
                 'not_refuted', 'internal_error'}, 'known unresolved code')
    return Unresolved(_KEY, kind='unresolved', payload={'status': code, 'detail': snapshot(detail),
        'target_checked': False, 'all_positive_widths': False})


def refutation(evidence):
    need(type(evidence) is ConcreteWitness and evidence.kind == 'concrete_witness',
         'only checked concrete evidence may refute a program')
    return evidence.data()
