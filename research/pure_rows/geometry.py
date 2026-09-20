"""Checked generated subalgebra, induced h, exact ambient kernel and saturation."""
from __future__ import annotations
import itertools
from .closure import check_closure
from .common import fields, integer, kernel_seeds, need, records, value, blocks, encoded


def verify_geometry(n: int, ops: list[dict], cells: list[tuple[int, int]], proof: dict) -> tuple:
    fields(proof, ('generation', 'h', 'kernel', 'forced_values', 'external_classes'))
    generation = proof['generation']
    need(type(generation) is list and len(generation) <= n, 'generated-domain event ceiling')
    h = [None] * n
    for event in generation:
        need(type(event) is list and bool(event), 'domain generation event')
        if event[0] == 'cell':
            need(len(event) == 2, 'domain cell event')
            a, out = cells[integer(event[1], 0, len(cells) - 1)]
        elif event[0] == 'native':
            need(len(event) == 3, 'domain native event')
            op = ops[integer(event[1], 0, len(ops) - 1)]
            args = event[2]
            need(type(args) is list and len(args) == op['arity'], 'domain operation arity')
            for x in args:
                integer(x, 0, n - 1)
                need(h[x] is not None, 'domain premise must already be generated')
            a, out = value(op['table'], args, n), value(op['table'], [h[x] for x in args], n)
        else:
            raise ValueError('unknown domain generation rule')
        need(h[a] is None, 'duplicate domain generation')
        h[a] = out
    need(type(proof['h']) is list and len(proof['h']) == n, 'homomorphism size')
    for y in proof['h']:
        if y is not None:
            integer(y, 0, n - 1)
    need(h == proof['h'], 'unjustified or omitted generated value')
    for a, c in cells:
        need(h[a] == c, 'supplied cell not realized on quotient')
    domain = [a for a in range(n) if h[a] is not None]
    for op in ops:
        for xs in itertools.product(domain, repeat=op['arity']):
            out = value(op['table'], xs, n)
            expected = value(op['table'], [h[x] for x in xs], n)
            need(h[out] == expected, 'domain is not closed or h not homomorphic')
    kappa = check_closure(n, records(n, ops), kernel_seeds(h), proof['kernel'])
    contact = {}
    for a in domain:
        key = kappa[a]
        need(key not in contact or contact[key] == h[a], 'kernel-extension obstruction remains')
        contact[key] = h[a]
    forced = [contact.get(kappa[a]) for a in range(n)]
    external = [block for block in blocks(kappa) if kappa[block[0]] not in contact]
    need(encoded(proof['forced_values']) == encoded(forced), 'forced domain/value must equal kernel saturation')
    need(encoded(proof['external_classes']) == encoded(external), 'external row classes wrong')
    return h, kappa, forced, external
