#!/usr/bin/env python3
"""Whole-word oracle versus ALL accepting paths of the new bit relation.

These finite checks test implementation fidelity and boundary mistakes. The
all-width justification is the induction in COUNT_MASK_PROOF.md, not testing.
"""
import argparse
import collections
import itertools
import json
import pickle
import random
import sys
import time
from pathlib import Path

from prefix_masks import Machine, lower, supported, shape, RUNS
from regular_interfaces import order, KB, word_target
from audit_fixed import validate_freeze
ROOT = Path(__file__).resolve().parent


def word_values(expr, values, width, operation):
    """Independent whole-word evaluation, using public tests/word_oracle.py."""
    env = {}; mask = (1 << width) - 1
    for t in order(expr):
        op = t[0]
        if op == 'var': v = values[t[1]]
        elif op == 'zero': v = 0
        elif op == 'ones': v = mask
        elif op == 'width': v = width
        elif op == 'const': v = t[1] & mask
        elif op in ('true', 'false'): v = int(op == 'true')
        elif op in RUNS:
            # A word-level reference for the compiled node; no bit-state logic.
            side = 'countr' if op.startswith('run_low_') else 'countl'
            desired = '_one' if op.endswith('one') else '_zero'
            n = operation(side + desired, [env[t[1]]], None, width)
            v = (1 << n) - 1
            if side == 'countl': v <<= width - n
        else:
            xs = [env[c] for c in t[1:]]
            if op == 'pair': v = tuple(xs)
            elif op == 'not': v = xs[0] ^ mask
            elif op.startswith('cmp'): v = int(operation('cmp', xs, int(op[3:]), width))
            else: v = operation(op, xs, None, width)
        env[t] = v
    return env


def accepted_outputs(machine, values, width):
    """Enumerate every branch, retain path multiplicities even when states merge."""
    paths = {(s, 0, 0, 0): 1 for s in machine.initial}
    peak = len(paths)
    for bit in range(width):
        end = bit == width - 1
        letter = tuple((v >> bit) & 1 for v in values)
        nxt_paths = collections.Counter()
        for (state, z, o, y), count in paths.items():
            for future in machine.futures(end):
                result = machine.step(state, letter, end, future)
                if result is not None:
                    nxt, out, target_bit = result
                    nxt_paths[(nxt, z | (out[0] << bit), o | (out[1] << bit), y | (target_bit << bit))] += count
        paths = nxt_paths; peak = max(peak, len(paths))
    outputs = collections.Counter()
    for (_, z, o, y), count in paths.items(): outputs[(z, o, y)] += count
    return outputs, peak


def assert_exact(machine, expr, values, width, operation, target='and'):
    expected = word_values(expr, values, width, operation)[expr]
    outputs, peak = accepted_outputs(machine, values, width)
    key = (*expected, word_target(target, values[4], values[5], width))
    if outputs != {key: 1}:
        raise AssertionError({'expr': expr, 'width': width, 'inputs': values,
                              'expected': key, 'accepted': repr(outputs)})
    return peak


def primitives(operation):
    x, y = ('var', 0), ('var', 1)
    expressions = []
    for side, counter, shift in [('low', 'countr', 'shl'), ('high', 'countl', 'lshr')]:
        for desired in ('one', 'zero'):
            count = (counter + '_' + desired, y)
            for action in ('clear', 'set'):
                expressions.append((action + '_' + side + '_bits', x, count))
            expressions.append((shift, ('ones',), count))
    checks = 0; peak = 0; by_form = {}
    for term in expressions:
        e = ('pair', ('zero',), term); machine = Machine(e, 'and'); n = 0
        for w in range(1, 7):
            for a, b in itertools.product(range(1 << w), repeat=2):
                peak = max(peak, assert_exact(machine, e, (a, b, 0, 0, 0, 0), w, operation)); n += 1
        by_form[term[0] + '__' + term[2][0]] = n; checks += n
    rng = random.Random(129031)
    wide_checks = 0
    for term in expressions:
        e = ('pair', ('zero',), term); machine = Machine(e, 'and')
        for w in (1, 2, 7, 64, 257):
            m = (1 << w) - 1
            for a, b in [(0, 0), (m, m), (m, 0), (0, m), (m, 1), (m, m ^ 1),
                         (m, 1 << (w - 1)), (m, m ^ (1 << (w - 1))),
                         (rng.getrandbits(w), rng.getrandbits(w))]:
                assert_exact(machine, e, (a, b, 0, 0, 0, 0), w, operation); wide_checks += 1
    # Reject crossing ends and reject a surviving numeric use of a fused count.
    refused = 0
    for side, counter in [('low', 'countl'), ('high', 'countr')]:
        for desired, action in itertools.product(('one', 'zero'), ('clear', 'set')):
            assert not supported(('pair', ('zero',), (action + '_' + side + '_bits', x, (counter + '_' + desired, y))))
            refused += 1
    for c in ('countr_one', 'countr_zero', 'countl_one', 'countl_zero'):
        count = (c, y); side = 'low' if c.startswith('countr') else 'high'
        assert not supported(('pair', ('set_' + side + '_bits', x, count), count)); refused += 1
        both = ('pair', ('set_' + side + '_bits', x, count), ('clear_' + side + '_bits', y, count))
        s = shape(both, 'and'); assert s['low_runs'] + s['high_runs'] == 1
    # Deliberately broken kernels must fail the independent oracle.
    mutations = []
    class WrongHighEnd(Machine):
        def step(self, state, letter, end, future):
            if end: return super().step(state, letter, False, (0,) * (len(self.right) + len(self.high)))
            return super().step(state, letter, end, future)
    high = ('pair', ('zero',), ('set_high_bits', ('zero',), ('countl_one', y)))
    low = ('pair', ('zero',), ('set_low_bits', ('zero',), ('countr_one', y)))
    missing = Machine(high, 'and'); missing.initial = tuple(s for s in missing.initial if s[7] == (1,))
    wrong_low = Machine(low, 'and'); wrong_low.initial = tuple((*s[:6], (0,), *s[7:]) for s in wrong_low.initial)
    for label, machine, expr, vals in [
        ('wrong_high_terminal_boundary', WrongHighEnd(high, 'and'), high, (0, 7, 0, 0, 0, 0)),
        ('missing_high_initial_choice', missing, high, (0, 0, 0, 0, 0, 0)),
        ('wrong_low_initial_state', wrong_low, low, (0, 7, 0, 0, 0, 0))]:
        try: assert_exact(machine, expr, vals, 3, operation)
        except AssertionError: mutations.append(label)
        else: raise AssertionError('broken kernel accepted: ' + label)
    return dict(exhaustive_cases=checks, widths=list(range(1, 7)), by_form=by_form,
                wide_boundary_cases=wide_checks, widest_word=257, max_active_paths=peak,
                unsupported_forms_rejected=refused, faulty_kernels_detected=mutations)


def composites(operation):
    x, y, zero, one = ('var', 0), ('var', 1), ('zero',), ('const', 1)
    low = lambda z: ('set_low_bits', zero, ('countr_one', z))
    high = lambda z: ('set_high_bits', zero, ('countl_zero', z))
    terms = [high(low(x)), low(high(y)), high(high(x)),
             high(('add', x, y)), low(('sub', x, y)),
             high(('lshr', y, one)), ('lshr', high(x), one),
             high(('clear_sign_bit', x)), low(('set_sign_bit', y)),
             ('select', ('cmp2', high(x), low(y)), ('add', high(x), y), ('sub', low(y), x))]
    checks = peak = 0
    for term in terms:
        e = ('pair', ('not', term), term); machine = Machine(e, 'and')
        for w in range(1, 5):
            for a, b in itertools.product(range(1 << w), repeat=2):
                peak = max(peak, assert_exact(machine, e, (a, b, 0, 0, a, b), w, operation)); checks += 1
    return {'expressions': len(terms), 'widths': [1, 2, 3, 4], 'cases': checks, 'max_active_paths': peak}


def corpus(out, operation, evaluate, parse_bundle):
    with (out / 'local_cache.pkl').open('rb') as f: items = pickle.load(f)
    selected = [x for x in items if x['record']['role'] == 'component' and x['record']['regular_after']]
    records = []; all_cases = full_path_cases = peak = 0
    for item in selected:
        r = item['record']; expr = item['simple']; compiled = lower(expr)
        fs = parse_bundle(item['bundle']); count = path_count = 0
        has_runs = any(t[0] in RUNS for t in order(compiled))
        machine = Machine(expr, 'and') if has_runs else None
        for w in (2, 3):
            for rows in itertools.product(KB, repeat=2 * w):
                vals = tuple(sum(rows[2 * j + i // 2][i % 2] << j for j in range(w)) for i in range(4))
                original = evaluate(fs, [vals[:2], vals[2:]], w, r['entry'])
                values = (*vals, 0, 0)
                direct = word_values(compiled, values, w, operation)[compiled]
                assert direct == original, (r['operator'], r['entry'], w, vals, original, direct)
                count += 1
                if has_runs:
                    outputs, active = accepted_outputs(machine, values, w)
                    assert outputs == {(*original, 0): 1}, (r['operator'], r['entry'], w, vals, outputs, original)
                    peak = max(peak, active); path_count += 1
        all_cases += count; full_path_cases += path_count
        records.append({'operator': r['operator'], 'entry': r['entry'], 'word_cases': count,
                        'all_accepting_path_cases': path_count, 'has_run_nodes': has_runs})
        if has_runs: print(r['operator'], r['entry'], 'SSA and all accepting paths PASS', flush=True)
    return {'components': len(selected), 'components_with_run_nodes': sum(r['has_run_nodes'] for r in records),
            'widths': [2, 3], 'word_cases': all_cases, 'all_accepting_path_cases': full_path_cases,
            'max_active_paths': peak, 'records': records}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', type=Path, required=True)
    ap.add_argument('--results', type=Path, default=ROOT / 'results')
    ap.add_argument('--primitives-only', action='store_true')
    args = ap.parse_args(); repo = args.repo.resolve(); validate_freeze(repo)
    sys.path[:0] = [str(repo / 'src'), str(repo / 'tests')]
    from word_oracle import operation, evaluate
    from qkf_certifier.frontend import parse_bundle
    start = time.perf_counter(); result = {'status': 'PASS'}
    result['primitives'] = primitives(operation); print('Primitives PASS', flush=True)
    result['composites'] = composites(operation); print('Composites PASS', flush=True)
    if not args.primitives_only: result['corpus'] = corpus(args.results, operation, evaluate, parse_bundle)
    result['seconds'] = time.perf_counter() - start
    result['scope'] = 'Finite implementation regression; every accepted path counted. Not an all-width proof by testing.'
    args.results.mkdir(exist_ok=True, parents=True)
    name = 'semantics_primitives.json' if args.primitives_only else 'semantics.json'
    (args.results / name).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'corpus'}, indent=2))


if __name__ == '__main__': main()
