#!/usr/bin/env python3
"""Exact count-to-mask interfaces, consumed compositionally, for all w >= 1.

The numeric count is never encoded in the automaton. Low-end runs use a
two-state causal machine. High-end runs use a two-state relation with a
terminal boundary; nondeterminism guesses bits, never correctness verdicts.
Original rewriting and concrete target registries remain unchanged.
"""
import itertools
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'dependencies'))
import regular_interfaces as regular

BACKEND = 'qkf-count-mask-relation-v1'
RUNS = {'run_low_zero', 'run_low_one', 'run_high_zero', 'run_high_one'}
MASKS = {'clear_low_bits', 'set_low_bits', 'clear_high_bits', 'set_high_bits'}
COUNTS = {'countr_zero', 'countr_one', 'countl_zero', 'countl_one'}


def run_node(count):
    side = 'low' if count[0].startswith('countr') else 'high'
    desired = 'one' if count[0].endswith('one') else 'zero'
    return ('run_' + side + '_' + desired, lower(count[1]))


@lru_cache(None)
def lower(e):
    """Deterministic, source-derived lowering; unmatched uses remain unmatched.

    Identical run nodes share one state bit through structural DAG deduplication.
    Internal run nodes are not accepted as source syntax.
    """
    op = e[0]
    if op in RUNS:
        raise ValueError('internal run node in source expression')
    if op in regular.LEAVES:
        return e
    if op in MASKS and e[2][0] in COUNTS:
        same_end = (op.endswith('low_bits') and e[2][0].startswith('countr')) or (
                    op.endswith('high_bits') and e[2][0].startswith('countl'))
        if same_end:
            mask = run_node(e[2]); x = lower(e[1])
            return ('or', x, mask) if op.startswith('set') else ('and', x, ('not', mask))
    if op in {'shl', 'lshr'} and e[1] == ('ones',) and e[2][0] in COUNTS:
        same_end = (op == 'shl' and e[2][0].startswith('countr')) or (
                    op == 'lshr' and e[2][0].startswith('countl'))
        if same_end:
            return ('not', run_node(e[2]))
    xs = tuple(lower(c) for c in e[1:])
    if op in regular.MINMAX:
        a, b = xs; test = ('cmp2' if op[0] == 's' else 'cmp6', a, b)
        return ('select', test, a, b) if op.endswith('min') else ('select', test, b, a)
    return (op, *xs)


def allowed_node(t):
    return t[0] in regular.PLAIN | regular.COMPS | RUNS or (
        t[0] in {'shl', 'lshr', 'ashr'} and t[2] == ('const', 1))


def supported(e):
    return all(allowed_node(t) for t in regular.order(lower(e)))


def shape(e, target):
    nodes = regular.order(lower(e), lower(regular.target_expression(target)))
    counts = {
        'comparisons': sum(t[0] in regular.COMPS for t in nodes),
        'right_shifts': sum(t[0] in {'lshr', 'ashr'} for t in nodes),
        'low_runs': sum(t[0].startswith('run_low_') for t in nodes),
        'high_runs': sum(t[0].startswith('run_high_') for t in nodes),
    }
    counts['initial_states'] = 2 ** (counts['comparisons'] + counts['high_runs'])
    counts['nonterminal_attempts_per_state'] = 16 * 2 ** (counts['right_shifts'] + counts['high_runs'])
    return counts


class Machine:
    """Product of exact bit relations, reading from least to most significant.

    For a high run, state h_i is the mask at the CURRENT position. Guess
    h_{i+1}, check h_i = match(y_i) & h_{i+1}, and require h_w = 1.
    Low run state p_i records matching bits STRICTLY BEFORE this position:
    output p_i & match(y_i), which is also p_{i+1}; p_0 = 1.
    """
    def __init__(self, candidate, target):
        if candidate[0] != 'pair' or not supported(candidate):
            raise ValueError('unsupported candidate')
        self.candidate = lower(candidate)
        self.target = lower(regular.target_expression(target))
        self.nodes = regular.order(self.candidate, self.target)
        self.arith = [t for t in self.nodes if t[0] in {'add', 'sub'}]
        self.left = [t for t in self.nodes if t[0] == 'shl']
        self.right = [t for t in self.nodes if t[0] in {'lshr', 'ashr'}]
        self.comps = [t for t in self.nodes if t[0] in regular.COMPS]
        self.low = [t for t in self.nodes if t[0].startswith('run_low_')]
        self.high = [t for t in self.nodes if t[0].startswith('run_high_')]
        for attr, ns in [('ai', self.arith), ('li', self.left), ('ri', self.right),
                         ('ci', self.comps), ('loi', self.low), ('hi', self.high)]:
            setattr(self, attr, {t: i for i, t in enumerate(ns)})
        self.phase_limit = max([0] + [abs(t[1]).bit_length() for t in self.nodes if t[0] == 'const'])
        self.initial = tuple(
            (g, 0, (0,) * len(self.arith), (0,) * len(self.left),
             (-1,) * len(self.right), (0,) * len(self.comps),
             (1,) * len(self.low), h, 0)
            for g in itertools.product((0, 1), repeat=len(self.comps))
            for h in itertools.product((0, 1), repeat=len(self.high)))
        self.bound = (2 ** len(self.comps) * (self.phase_limit + 1) *
                      2 ** (len(self.arith) + len(self.left) + len(self.low) + len(self.high) + 1) *
                      3 ** (len(self.right) + len(self.comps)))

    def step(self, state, letter, end, future):
        guesses, phase, carries, delay, pending, rels, low, high, bad = state
        values = {}; nc = list(carries); nd = list(delay); np = list(pending)
        nr = list(rels); nl = list(low); nh = list(high)
        for t in self.nodes:
            op = t[0]
            if op == 'var': v = letter[t[1]]
            elif op == 'const': v = (t[1] >> phase) & 1
            elif op in {'zero', 'false'}: v = 0
            elif op in {'ones', 'true'}: v = 1
            elif op == 'pair': v = (values[t[1]], values[t[2]])
            elif op == 'not': v = 1 ^ values[t[1]]
            elif op.startswith('run_low_'):
                i = self.loi[t]; desired = int(op.endswith('one'))
                v = low[i] & int(values[t[1]] == desired); nl[i] = v
            elif op.startswith('run_high_'):
                i = self.hi[t]; desired = int(op.endswith('one'))
                next_mask = 1 if end else future[len(self.right) + i]
                if high[i] != (int(values[t[1]] == desired) & next_mask): return None
                v = high[i]; nh[i] = next_mask
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
                    v = (a if op == 'ashr' else 0) if end else future[i]; np[i] = v
                elif op in regular.COMPS:
                    i = self.ci[t]; nr[i] = (a - b) if a != b else rels[i]; v = guesses[i]
                    if end and bool(v) != regular.compare(int(op[3:]), nr[i], a, b): return None
                else: raise ValueError(op)
            values[t] = v
        z, o = values[self.candidate]; y = values[self.target]
        bad = int(bool(bad or (z & y) or (o & (1 ^ y))))
        return ((guesses, min(phase + 1, self.phase_limit), tuple(nc), tuple(nd),
                 tuple(np), tuple(nr), tuple(nl), tuple(nh), bad), (z, o), y)

    def futures(self, end):
        n = len(self.right) + len(self.high)
        return ((0,) * n,) if end else itertools.product((0, 1), repeat=n)

    def successors(self, state, end):
        for li, letter in enumerate(regular.LETTERS):
            for g in self.futures(end):
                result = self.step(state, letter, end, g)
                if result is not None: yield li, g, result
