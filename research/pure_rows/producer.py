"""Certificate production for Paper I's pure-row fragment.

Structural search adapts feedback/row_geometry from the preserved Paper I
supplement. The additional interface trace is an intentionally redundant lower
proof; it is not used to guess the structural carrier quotient. No completion
is selected by this algorithm. See README_RU.md for the exact reuse boundary.
"""
from __future__ import annotations
import itertools
import time
from .common import (CERTIFICATE, DSU, Exhausted, InputError, InvalidCertificate, SizeLimit, MAX_NAMES, blocks,
                     canonical, digest, integer, kernel_seeds, lift_seeds, need,
                     presentation, quotient, records, value)
from .model import build_model


class Budget:
    def __init__(self, options=None):
        defaults = dict(max_events=100_000, max_work=5_000_000, max_rounds=MAX_NAMES)
        if options is not None:
            if type(options) is not dict or not set(options) <= set(defaults):
                raise InputError('unknown production resource limit')
            for name, val in options.items():
                try:
                    integer(val, 0, defaults[name] if name != 'max_work' else 20_000_000)
                except ValueError as exc:
                    raise InputError(str(exc)) from exc
            defaults.update(options)
        self.limits = defaults
        self.used = dict(events=0, work=0, rounds=0)
        self.stage = 'initialization'

    def charge(self, name: str, amount: int = 1) -> None:
        nxt = self.used[name] + amount
        limit = self.limits['max_' + name]
        if nxt > limit:
            raise Exhausted(self.stage, name, nxt, limit)
        self.used[name] = nxt


def derive_closure(size: int, native: list[tuple], seeds: list[tuple[int, int]],
                   budget: Budget, feedback: tuple[int, int] | None = None) -> dict:
    uf = DSU(size)
    events = []

    def merge(a, b, reason):
        if uf.find(a) == uf.find(b):
            return False
        budget.charge('events')
        uf.union(a, b)
        events.append(reason)
        return True

    for i, (a, b) in enumerate(seeds):
        budget.charge('work')
        merge(a, b, ['seed', i])
    while True:
        changed = False
        seen = {}
        for i, (op, args, result) in enumerate(native):
            budget.charge('work', len(args) + 1)
            key = (op, tuple(uf.find(a) for a in args))
            if key in seen:
                j = seen[key]
                changed |= merge(result, native[j][2], ['native', i, j])
            else:
                seen[key] = i
        if feedback is not None:
            n, nb = feedback
            for row in range(nb):
                first = {}
                for a in range(n):
                    budget.charge('work')
                    key = uf.find(a)
                    if key in first:
                        other = first[key]
                        changed |= merge((row + 1) * n + a, (row + 1) * n + other,
                                         ['feedback', row, a, other])
                    else:
                        first[key] = a
        if not changed:
            return dict(partition=uf.labels(), events=events)


def feedback(p: dict, budget: Budget) -> tuple:
    n, nb = len(p['carrier']['names']), len(p['operators']['names'])
    ops = p['carrier']['operations']
    theta = list(range(n))
    stages = []
    while True:
        budget.stage = 'structural_feedback'
        budget.charge('rounds')  # includes the final non-strict fixed-point check
        qn, qops = quotient(n, ops, theta)
        local = []
        kernels = []
        for b in range(nb):
            seeds = [(qn + theta[a], theta[c]) for bb, a, c in p['cells'] if bb == b]
            proof = derive_closure(2 * qn, records(qn, qops, 2), seeds, budget)
            local.append(proof)
            kernels.append(canonical(proof['partition'][:qn]))
        join = derive_closure(n, records(n, ops), lift_seeds(theta, kernels), budget)
        stages.append(dict(carrier_partition=theta, pushouts=local, join=join))
        nxt = join['partition']
        if nxt == theta:
            return theta, stages
        need(len(set(nxt)) < len(set(theta)), 'internal feedback progress invariant')
        theta = nxt


def geometry(n: int, ops: list[dict], cells: list[tuple[int, int]], budget: Budget) -> dict:
    budget.stage = 'row_geometry'
    h = [None] * n
    events = []

    def add(a, out, reason):
        need(h[a] is None or h[a] == out, 'internal stabilized row incoherence')
        if h[a] is not None:
            return False
        budget.charge('events')
        h[a] = out
        events.append(reason)
        return True

    for i, (a, out) in enumerate(cells):
        budget.charge('work')
        add(a, out, ['cell', i])
    while True:
        changed = False
        domain = [a for a in range(n) if h[a] is not None]
        for oi, op in enumerate(ops):
            for args in itertools.product(domain, repeat=op['arity']):
                budget.charge('work', len(args) + 1)
                a, out = value(op['table'], args, n), value(op['table'], [h[x] for x in args], n)
                changed |= add(a, out, ['native', oi, list(args)])
        if not changed:
            break
    kernel = derive_closure(n, records(n, ops), kernel_seeds(h), budget)
    kappa = kernel['partition']
    contact = {}
    for a, out in enumerate(h):
        if out is not None:
            need(kappa[a] not in contact or contact[kappa[a]] == out, 'internal kernel-extension obstruction')
            contact[kappa[a]] = out
    return dict(generation=events, h=h, kernel=kernel,
                forced_values=[contact.get(kappa[a]) for a in range(n)],
                external_classes=[xs for xs in blocks(kappa) if kappa[xs[0]] not in contact])


def produce(raw_input, limits=None) -> tuple[dict, dict | None, dict]:
    """All productive work is budgeted; exhaustion never exports partial evidence."""
    p = presentation(raw_input)
    budget = Budget(limits)
    started = time.perf_counter()
    try:
        theta, stages = feedback(p, budget)
        n, nb = len(p['carrier']['names']), len(p['operators']['names'])
        qn, qops = quotient(n, p['carrier']['operations'], theta)
        rows = [geometry(qn, qops, [(theta[a], theta[c]) for bb, a, c in p['cells'] if bb == b], budget)
                for b in range(nb)]
        levels = []
        from .checker import interface_data, _check, check
        for h in (1, 2):
            budget.stage = 'interface_derivations'
            size, native, seeds, fb = interface_data(p, h)
            proof = derive_closure(size, native, seeds, budget, fb)
            levels.append(dict(horizon=h, equality=proof, model=build_model(p, proof['partition'], h)))
        cert = dict(schema=CERTIFICATE, input_sha256=digest(p), feedback=stages,
                    rows=rows, levels=levels, result=None)
        built = time.perf_counter()
        # _check validates every structural/trace/model premise and computes the
        # result; public check additionally compares the saved result field.
        cert['result'] = _check(p, cert)
        try:
            result = check(p, cert)
        except InvalidCertificate as exc:
            if isinstance(exc.__cause__, SizeLimit):
                limit = exc.__cause__
                raise Exhausted('certificate_encoding', limit.resource, limit.used, limit.limit) from exc
            raise
        checked = time.perf_counter()
        diagnostics = dict(status='completed', limits=budget.limits, work=budget.used,
                           production_seconds=built - started, builtin_validation_seconds=checked - built,
                           cost_scope='work units count search scans and successful events, not checker/runtime instructions')
        return result, cert, diagnostics
    except Exhausted as exc:
        return dict(exc.record, input_sha256=digest(p), complete=False), None, dict(
            status='incomplete', limits=budget.limits, work=budget.used,
            elapsed_seconds=time.perf_counter() - started)


def prove(raw_input, limits=None) -> tuple[dict, dict | None]:
    result, proof, _ = produce(raw_input, limits)
    return result, proof
