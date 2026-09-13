#!/usr/bin/env python3
"""Research-only finite relation interface; no SMT dependency.

Words are read LSB first. Guesses for whole-word comparisons are checked at
the last bit. A pending bit checks a right shift; a stored bit checks a left
shift. Certificates are closed finite invariants, not trusted search verdicts.
The transition interpreter remains in the trusted Python implementation.
"""
import itertools
from functools import lru_cache

PIN = 'f93561682319e8b911ed32c01583f2a496dc59fc'
SCHEMA = 'qkf-regular-invariant-research-v2'
SEMANTICS = 'positive-width; nonbottom-KB; total-transfer-words-v2; target-defined-by-this-module'
KB = ((1, 0), (0, 1), (0, 0))
# Six bits: za, oa, zb, ob, concrete a, concrete b. Exactly 16 valid letters.
LETTERS = tuple(ka + kb + (a, b) for ka, kb in itertools.product(KB, repeat=2)
                for a, b in itertools.product((0, 1), repeat=2)
                if not ka[0] & a and ka[1] & a == ka[1]
                and not kb[0] & b and kb[1] & b == kb[1])
assert len(LETTERS) == 16
LEAVES = {'var', 'zero', 'ones', 'const', 'true', 'false'}
PLAIN = LEAVES | {'pair', 'not', 'and', 'or', 'xor', 'add', 'sub', 'select',
                   'booland', 'boolor', 'boolxor', 'clear_sign_bit', 'set_sign_bit'}
COMPS = {'cmp' + str(i) for i in range(10)}
MINMAX = {'umin', 'umax', 'smin', 'smax'}


def tree(e):
    return tuple(tree(x) if isinstance(x, (list, tuple)) else x for x in e)


def order(*roots):
    result = []; seen = set()
    def visit(t):
        if t in seen: return
        if t[0] not in LEAVES:
            for x in t[1:]:
                if isinstance(x, tuple): visit(x)
        seen.add(t); result.append(t)
    for root in roots: visit(root)
    return result


def supported(e):
    return all(t[0] in PLAIN | COMPS | MINMAX or
               (t[0] in {'shl', 'lshr', 'ashr'} and t[2] == ('const', 1))
               for t in order(e))


@lru_cache(None)
def lower(e):
    if e[0] in LEAVES: return e
    op = e[0]; xs = tuple(lower(x) for x in e[1:])
    if op in MINMAX:
        a, b = xs; c = ('cmp2' if op[0] == 's' else 'cmp6', a, b)
        return ('select', c, a, b) if op.endswith('min') else ('select', c, b, a)
    return (op, *xs)


def target_expression(target):
    a, b = ('var', 4), ('var', 5)
    if target in {'and', 'or', 'xor', 'add', 'sub'} | MINMAX: return (target, a, b)
    if target == 'uadd_sat':
        s = ('add', a, b)
        return ('select', ('cmp6', s, a), ('ones',), s)
    if target == 'usub_sat':
        return ('select', ('cmp6', a, b), ('zero',), ('sub', a, b))
    raise ValueError('unsupported target: ' + target)


def target_for(operator):
    name = operator.removeprefix('KnownBits_')
    simple = {'And': 'and', 'Or': 'or', 'Xor': 'xor', 'Add': 'add', 'Sub': 'sub',
              'Smin': 'smin', 'Smax': 'smax', 'Umin': 'umin', 'Umax': 'umax',
              'UaddSat': 'uadd_sat', 'UsubSat': 'usub_sat'}
    if name in simple: return simple[name], 'explicit_total_target'
    if name.startswith('Add'): return 'add', 'stronger_unconditional_modular_target_flags_not_modeled'
    if name.startswith('Sub'): return 'sub', 'stronger_unconditional_modular_target_flags_not_modeled'
    return None, 'unsupported_target'


def word_target(target, a, b, w):
    mask = (1 << w) - 1
    signed = lambda x: x - (1 << w) if x & (1 << (w - 1)) else x
    if target == 'and': return a & b
    if target == 'or': return a | b
    if target == 'xor': return a ^ b
    if target == 'add': return (a + b) & mask
    if target == 'sub': return (a - b) & mask
    if target == 'umin': return min(a, b)
    if target == 'umax': return max(a, b)
    if target == 'smin': return min(a, b, key=signed)
    if target == 'smax': return max(a, b, key=signed)
    if target == 'uadd_sat': return min(a + b, mask)
    if target == 'usub_sat': return max(a - b, 0)
    raise ValueError(target)


def compare(pred, rel, a, b):
    signed_rel = b - a if a != b else rel  # a,b are the FINAL/sign bits.
    return (rel == 0, rel != 0, signed_rel < 0, signed_rel <= 0,
            signed_rel > 0, signed_rel >= 0, rel < 0, rel <= 0,
            rel > 0, rel >= 0)[pred]


class Machine:
    def __init__(self, candidate, target):
        if candidate[0] != 'pair' or not supported(candidate):
            raise ValueError('unsupported candidate')
        self.candidate = lower(candidate); self.target = lower(target_expression(target))
        self.nodes = order(self.candidate, self.target)
        self.arith = [t for t in self.nodes if t[0] in {'add', 'sub'}]
        self.left = [t for t in self.nodes if t[0] == 'shl']
        self.right = [t for t in self.nodes if t[0] in {'lshr', 'ashr'}]
        self.comps = [t for t in self.nodes if t[0] in COMPS]
        self.ai = {t: i for i, t in enumerate(self.arith)}
        self.li = {t: i for i, t in enumerate(self.left)}
        self.ri = {t: i for i, t in enumerate(self.right)}
        self.ci = {t: i for i, t in enumerate(self.comps)}
        self.phase_limit = max([0] + [abs(t[1]).bit_length() for t in self.nodes if t[0] == 'const'])
        self.guesses = tuple(itertools.product((0, 1), repeat=len(self.comps)))
        self.right_guesses = tuple(itertools.product((0, 1), repeat=len(self.right)))
        self.initial = tuple((g, 0, (0,) * len(self.arith), (0,) * len(self.left),
                              (-1,) * len(self.right), (0,) * len(self.comps), 0)
                             for g in self.guesses)
        self.bound = (2 ** len(self.comps) * (self.phase_limit + 1) *
                      2 ** (len(self.arith) + len(self.left) + 1) *
                      3 ** (len(self.right) + len(self.comps)))

    def step(self, state, letter, end, right_guess):
        guesses, phase, carries, delay, pending, rels, bad = state
        values = {}; nc = list(carries); nd = list(delay); np = list(pending); nr = list(rels)
        for t in self.nodes:
            op = t[0]
            if op == 'var': v = letter[t[1]]
            elif op == 'const': v = (t[1] >> phase) & 1
            elif op in {'zero', 'false'}: v = 0
            elif op in {'ones', 'true'}: v = 1
            elif op == 'pair': v = (values[t[1]], values[t[2]])
            elif op == 'not': v = 1 ^ values[t[1]]
            elif op in {'clear_sign_bit', 'set_sign_bit'}:
                v = int(op == 'set_sign_bit') if end else values[t[1]]
            elif op == 'select': v = values[t[2]] if values[t[1]] else values[t[3]]
            else:
                a, b = values[t[1]], values[t[2]]
                if op in {'and', 'booland'}: v = a & b
                elif op in {'or', 'boolor'}: v = a | b
                elif op in {'xor', 'boolxor'}: v = a ^ b
                elif op in {'add', 'sub'}:
                    i = self.ai[t]; z = a + b + carries[i] if op == 'add' else a - b - carries[i]
                    v = z & 1; nc[i] = z >> 1 if op == 'add' else int(z < 0)
                elif op == 'shl':
                    i = self.li[t]; v = delay[i]; nd[i] = a
                elif op in {'lshr', 'ashr'}:
                    i = self.ri[t]
                    if pending[i] != -1 and pending[i] != a: return None
                    v = (a if op == 'ashr' else 0) if end else right_guess[i]
                    np[i] = v
                elif op in COMPS:
                    i = self.ci[t]; nr[i] = (a - b) if a != b else rels[i]; v = guesses[i]
                    if end and bool(v) != compare(int(op[3:]), nr[i], a, b): return None
                else: raise ValueError(op)
            values[t] = v
        z, o = values[self.candidate]; y = values[self.target]
        bad = int(bool(bad or (z & y) or (o & (1 ^ y))))
        return ((guesses, min(phase + 1, self.phase_limit), tuple(nc), tuple(nd),
                 tuple(np), tuple(nr), bad), (z, o), y)

    def successors(self, state, end):
        for li, letter in enumerate(LETTERS):
            for g in (((0,) * len(self.right),) if end else self.right_guesses):
                result = self.step(state, letter, end, g)
                if result is not None: yield li, g, result


def discover(machine, max_states=20000):
    states = list(machine.initial); parents = {s: None for s in states}; edges = 0
    for state in states:
        for li, rg, (nxt, _, _) in machine.successors(state, True):
            edges += 1
            if nxt[-1]:
                letters = [li]; p = state
                while parents[p] is not None:
                    p, previous_letter = parents[p]; letters.append(previous_letter)
                return {'status': 'counterexample', 'states_explored': len(states),
                        'letters': list(reversed(letters)), 'transitions_examined': edges}
        for li, rg, (nxt, _, _) in machine.successors(state, False):
            edges += 1
            if nxt not in parents:
                if len(states) >= max_states:
                    return {'status': 'budget_exceeded', 'states_explored': len(states)}
                parents[nxt] = state, li; states.append(nxt)
    assert len(states) <= machine.bound
    return {'status': 'proved_sound', 'states': states, 'state_count': len(states),
            'transitions_examined': edges, 'state_bound': machine.bound}


def check_invariant(machine, proposed_states):
    """No BFS/search, no trusted verdict or transition table from the producer."""
    states = {tree(s) for s in proposed_states}
    if not states or not set(machine.initial) <= states: raise ValueError('missing initial state')
    checks = 0
    for state in states:
        for _, _, (nxt, _, _) in machine.successors(state, True):
            checks += 1
            if nxt[-1]: raise ValueError('accepting error')
        for _, _, (nxt, _, _) in machine.successors(state, False):
            checks += 1
            if nxt not in states: raise ValueError('invariant is not closed')
    return checks


def check_certificate(bundle, entry, certificate, expected_target):
    from qkf_certifier.kernel import replay, digest
    if certificate['schema'] != SCHEMA or certificate['semantics'] != SEMANTICS:
        raise ValueError('research contract mismatch')
    if certificate['entry'] != entry or certificate['normalization']['entry'] != entry:
        raise ValueError('entry mismatch')
    if certificate['target'] != expected_target:
        raise ValueError('target mismatch')
    nf = replay(bundle, entry, certificate['normalization'])
    if digest(nf) != certificate['normal_form_hash']: raise ValueError('normal form mismatch')
    return check_invariant(Machine(nf, certificate['target']), certificate['invariant'])
