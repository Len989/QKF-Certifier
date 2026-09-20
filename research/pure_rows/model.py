"""Sparse-with-default TOTAL separating models, evaluated on every input axiom.

Default completion is a witness construction, not canonical information forced
by initial semantics. At horizon one the model need NOT satisfy compatibility.
At horizon two it satisfies the entire declared pure-row theory.
"""
from __future__ import annotations
import itertools
from .common import fields, integer, need, records, value


def build_model(p: dict, labels: list[int], horizon: int) -> dict:
    n, nb = len(p['carrier']['names']), len(p['operators']['names'])
    operations = p['carrier']['operations']
    slots = [{} for _ in operations]
    for oi, args, result in records(n, operations, 1 if horizon == 1 else nb + 1):
        key, out = tuple(labels[a] for a in args), labels[result]
        need(key not in slots[oi] or slots[oi][key] == out, 'model native ambiguity')
        slots[oi][key] = out
    alpha = {}
    for b in range(nb):
        for a in range(n):
            key, out = (b, labels[a]), labels[(b + 1) * n + a]
            need(key not in alpha or alpha[key] == out, 'model action ambiguity')
            alpha[key] = out
    return dict(A_size=len(set(labels)), B_size=nb,
                carrier_values=labels[:n], B_operations=p['operators']['operations'],
                A_operations=[dict(name=op['name'], arity=op['arity'], default=0,
                                   entries=[[list(xs), out] for xs, out in sorted(slots[oi].items())])
                              for oi, op in enumerate(operations)],
                alpha=dict(default=0, entries=[[list(xs), out] for xs, out in sorted(alpha.items())]))


def verify_model(p: dict, model: dict, horizon: int, labels: list[int]) -> dict:
    """No congruence closure: validate interpretation and evaluate all axioms."""
    fields(model, ('A_size', 'B_size', 'carrier_values', 'A_operations', 'B_operations', 'alpha'))
    n, nb = len(p['carrier']['names']), len(p['operators']['names'])
    size = integer(model['A_size'], 1, n * (nb + 1))
    need(size == len(set(labels)), 'separation model domain size')
    need(type(model['B_size']) is int and model['B_size'] == nb, 'operator model size')
    values = model['carrier_values']
    need(type(values) is list and len(values) == n, 'carrier interpretation size')
    for x in values:
        integer(x, 0, size - 1)
    need(type(model['A_operations']) is list and len(model['A_operations']) == len(p['carrier']['operations']),
         'native model signature')

    def sparse(obj, bounds):
        fields(obj, ('default', 'entries'))
        default = integer(obj['default'], 0, size - 1)
        need(type(obj['entries']) is list and len(obj['entries']) <= 200_000, 'sparse model size')
        table = {}
        previous = None
        for entry in obj['entries']:
            need(type(entry) is list and len(entry) == 2, 'sparse entry')
            args, out = entry
            need(type(args) is list and len(args) == len(bounds), 'sparse tuple arity')
            key = tuple(integer(x, 0, bound - 1) for x, bound in zip(args, bounds))
            integer(out, 0, size - 1)
            need(previous is None or previous < key, 'duplicate/noncanonical sparse entries')
            previous = key
            table[key] = out
        return lambda xs: table.get(tuple(xs), default)

    functions = []
    for given, op in zip(model['A_operations'], p['carrier']['operations']):
        fields(given, ('name', 'arity', 'default', 'entries'))
        need(given['name'] == op['name'] and type(given['arity']) is int and given['arity'] == op['arity'],
             'native interpretation identity')
        functions.append(sparse(dict(default=given['default'], entries=given['entries']), [size] * op['arity']))
    # The operator domain consists exactly of its names; these complete tables
    # interpret every operator tuple. No action composition rule follows from it.
    from .common import encoded
    need(encoded(model['B_operations']) == encoded(p['operators']['operations']), 'operator diagram changed')
    alpha = sparse(model['alpha'], [nb, size])
    cells = [[alpha((b, values[a])) for a in range(n)] for b in range(nb)]
    actual = values + [x for row in cells for x in row]
    need(actual == labels, 'model does not separate exactly the named interface classes')
    native_count = 0
    compatibility_count = 0
    for oi, op in enumerate(p['carrier']['operations']):
        for xs, y in zip(itertools.product(range(n), repeat=op['arity']), op['table']):
            need(functions[oi]([values[x] for x in xs]) == values[y], 'native diagram false in model')
            native_count += 1
            if horizon == 2:
                for b in range(nb):
                    # Evaluate RAW alpha(b, f(named tuple)), not a guessed row table.
                    left = alpha((b, functions[oi]([values[x] for x in xs])))
                    right = functions[oi]([alpha((b, values[x])) for x in xs])
                    need(left == right, 'compatibility axiom false in model')
                    compatibility_count += 1
    for b, a, c in p['cells']:
        need(alpha((b, values[a])) == values[c], 'supplied cell false in model')
    return dict(carrier_diagram=native_count,
                operator_diagram=sum(len(op['table']) for op in p['operators']['operations']),
                supplied_occurrences=len(p['cells']), compatibility=compatibility_count)
