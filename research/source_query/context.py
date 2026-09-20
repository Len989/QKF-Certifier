"""Whole selected-method admission and the independent signed target domain."""
from dataclasses import dataclass

from research.semantic_work.contract import snapshot, digest, canonical, load_json, save_json
from research.ground_query.schema import fields, require, index
from research.signed_predicates.frontend import CONTRACT, goal, target_value
from research.signed_bridge.model import read, request as source_selection
from research.unified.v3_schema import compile_target, SIGNED_KIND

REQUEST = 'qkf-guarded-source-query-v1'
PROOF = 'qkf-guarded-source-proof-v1'
RULESET = 'signed-ground-native-rules-v1'
MAX_WIDTH = 4096


def integer(value, lo, hi, message):
    require(type(value) is int and lo <= value <= hi, message)
    return value


def target_domain(limit, width):
    """Exact capped-popcount/last-bit classes of positive-width words.

    This explores only the fixed, source-free target abstraction (at most ten
    states). It never executes the source or builds its residual interface.
    """
    states = {(0, 0)}
    edges = 0
    if width is not None:
        for _ in range(width):
            edges += 2 * len(states)
            states = {(min(limit, c + b), b) for c, _ in states for b in (0, 1)}
    else:
        states = {(0, 0), (min(limit, 1), 1)}
        while True:
            edges += 2 * len(states)
            following = states | {(min(limit, c + b), b) for c, _ in states for b in (0, 1)}
            if following == states:
                break
            states = following
    return tuple(sorted(states)), edges


@dataclass
class Context:
    request: dict
    selection: dict
    ir: dict
    spec: dict
    guards: list
    width: object
    limit: int
    domain: tuple
    domain_edges: int

    def guard(self, count, sign):
        return all(target_value(g, count, sign) for g in self.guards)

    def binding(self):
        return {'source_sha256': self.ir['source_sha256'], 'ir_sha256': digest(self.ir),
                'request_sha256': digest(self.request), 'contract': CONTRACT, 'ruleset': RULESET}


def prepare(source, raw):
    r = snapshot(raw)
    fields(r, ('schema', 'target', 'guards', 'width'), 'source query')
    require(r['schema'] == REQUEST, 'source query schema')
    compiled = compile_target(r['target'])
    require(compiled['kind'] == SIGNED_KIND and r['target']['schema'] == 'qkf-target-v2',
            'signed qkf-target-v2 required')
    spec = compiled['specification']
    require(type(r['guards']) is list and len(r['guards']) <= 16, 'guard conjunction budget')
    limits = [goal(spec)]
    for guard in r['guards']:
        limits.append(goal({**spec, 'target': guard}))
    w = r['width']
    require(type(w) is dict and w.get('kind') in ('all_positive', 'fixed'), 'width scope')
    if w['kind'] == 'all_positive':
        fields(w, ('kind',), 'all-positive width')
        width = None
    else:
        fields(w, ('kind', 'bits'), 'fixed width')
        width = integer(w['bits'], 1, MAX_WIDTH, 'fixed width 1..4096')
    selection = source_selection(spec['entry'], spec['word_type'])
    # Admit every statement in the selected method BEFORE any local or vacuous proof.
    ir = read(source, selection)
    limit = max(limits)
    states, edges = target_domain(limit, width)
    domain = tuple(s for s in states if all(target_value(g, *s) for g in r['guards']))
    return Context(r, selection, ir, spec, r['guards'], width, limit, domain, edges)


def make_request(target, guards=None, width=None):
    return {'schema': REQUEST, 'target': target, 'guards': [] if guards is None else guards,
            'width': {'kind': 'all_positive'} if width is None else {'kind': 'fixed', 'bits': width}}
