"""Strict finite presentation and elementary shared data operations.

The carrier/operator signatures are separate; names are NOT nullary native
operations. Native tables constrain named inputs only. No action laws are added.
Algorithms adapt Paper I's MIT verify_article.py; see README_RU.md provenance.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

INPUT = 'qkf-pure-row-input-v1'
THEORY = 'typed-ground-pure-rows-v1'
CERTIFICATE = 'qkf-pure-row-certificate-v1'
RESULT = 'qkf-pure-row-result-v1'
MAX_JSON_BYTES = 32_000_000
MAX_JSON_NODES = 2_000_000
MAX_NAMES = 32
MAX_TABLE = 8192
MAX_RECORDS = 200_000


class InputError(ValueError):
    """Input is outside the explicit finite schema/profile."""


class InvalidCertificate(ValueError):
    """Claimed evidence is malformed, unbound, unsound, or incomplete."""


class SizeLimit(ValueError):
    def __init__(self, resource: str, used: int, limit: int):
        super().__init__(f'{resource} ceiling: {used} > {limit}')
        self.resource, self.used, self.limit = resource, used, limit


class Exhausted(Exception):
    def __init__(self, stage: str, resource: str, used: int, limit: int):
        super().__init__(f'{stage}: {resource} {used} > {limit}')
        self.record = dict(status='budget_exhausted', stage=stage,
                           resource=resource, used=used, limit=limit)


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def fields(obj: Any, keys: tuple[str, ...] | list[str]) -> None:
    need(type(obj) is dict and set(obj) == set(keys), 'missing/unknown object fields')


def integer(value: Any, low: int, high: int) -> int:
    need(type(value) is int and low <= value <= high, f'integer outside [{low}, {high}]')
    return value


def snapshot(obj: Any) -> Any:
    """Reject non-JSON/Python alias tricks, booleans-as-indices and huge inputs.

    Integers and booleans remain different in encoding. Lists may share backing
    objects, but expanded occurrences count separately. Active cycles are rejected.
    """
    count = 0
    size = 0
    active: set[int] = set()

    def visit(x: Any, depth: int) -> Any:
        nonlocal count, size
        count += 1
        if count > MAX_JSON_NODES:
            raise SizeLimit('JSON_nodes', count, MAX_JSON_NODES)
        if depth > 80:
            raise SizeLimit('JSON_depth', depth, 80)
        if x is None or type(x) is bool:
            size += 5
            out = x
        elif type(x) is int:
            need(x.bit_length() <= 128, 'oversized integer')
            size += 40
            out = x
        elif type(x) is str:
            size += len(x.encode('utf-8')) + 2
            out = x
        elif type(x) in (list, dict):
            need(id(x) not in active, 'cyclic input')
            active.add(id(x))
            if type(x) is list:
                out = [visit(y, depth + 1) for y in x]
            else:
                need(all(type(k) is str for k in x), 'non-string key')
                out = {visit(k, depth + 1): visit(v, depth + 1) for k, v in x.items()}
            active.remove(id(x))
            size += len(x) + 2
        else:
            raise ValueError('non-JSON value type')
        if size > MAX_JSON_BYTES:
            raise SizeLimit('conservative_JSON_size', size, MAX_JSON_BYTES)
        return out

    return visit(obj, 0)


def encoded(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(obj: Any) -> str:
    return hashlib.sha256(encoded(obj)).hexdigest()


def read_json(path: str | Path) -> Any:
    raw = Path(path).read_bytes()
    need(len(raw) <= MAX_JSON_BYTES, 'wire JSON size ceiling')

    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, 'duplicate JSON key')
            out[key] = value
        return out

    def bad(value):
        raise ValueError('nonfinite JSON value: ' + value)

    def number(text):
        need(len(text.lstrip('-')) <= 40, 'oversized integer token')
        return int(text)

    try:
        return snapshot(json.loads(raw, object_pairs_hook=pairs, parse_constant=bad, parse_int=number))
    except RecursionError as exc:
        raise ValueError('JSON nesting ceiling') from exc


def write_json(path: str | Path, value: Any) -> None:
    """Never overwrite another proof; no parent-directory creation is implicit."""
    data = encoded(snapshot(value)) + b'\n'
    with Path(path).open('xb') as stream:
        stream.write(data)


def presentation(raw: Any) -> dict:
    try:
        p = snapshot(raw)
        fields(p, ('schema', 'theory', 'carrier', 'operators', 'cells'))
        need(p['schema'] == INPUT and p['theory'] == THEORY, 'unsupported presentation theory')
        for sort in ('carrier', 'operators'):
            algebra = p[sort]
            fields(algebra, ('names', 'operations'))
            names = algebra['names']
            need(type(names) is list and 1 <= len(names) <= MAX_NAMES, 'sort size ceiling')
            need(all(type(x) is str and 0 < len(x.encode('utf-8')) <= 128 for x in names), 'name')
            need(len(set(names)) == len(names), 'duplicate names within a sort')
            operations = algebra['operations']
            need(type(operations) is list and len(operations) <= 16, 'operation count ceiling')
            seen = set()
            total = 0
            for op in operations:
                fields(op, ('name', 'arity', 'table'))
                name = op['name']
                need(type(name) is str and 0 < len(name.encode('utf-8')) <= 128, 'operation name')
                need(name not in seen, 'duplicate operation symbol within sort')
                seen.add(name)
                arity = integer(op['arity'], 1, 4)
                need(len(names) ** arity <= MAX_TABLE, 'native table ceiling')
                need(type(op['table']) is list and len(op['table']) == len(names) ** arity,
                     'native table must be complete in lexicographic tuple order')
                for x in op['table']:
                    integer(x, 0, len(names) - 1)
                total += len(op['table'])
            need(total <= MAX_TABLE, 'total native table ceiling')
        n, nb = len(p['carrier']['names']), len(p['operators']['names'])
        need((nb + 1) * sum(len(op['table']) for op in p['carrier']['operations']) <= MAX_RECORDS,
             'represented native record ceiling')
        need(type(p['cells']) is list and len(p['cells']) <= 4096, 'cell occurrence ceiling')
        for cell in p['cells']:
            need(type(cell) is list and len(cell) == 3, 'cell occurrence shape')
            integer(cell[0], 0, nb - 1)
            integer(cell[1], 0, n - 1)
            integer(cell[2], 0, n - 1)
        return p
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError) as exc:
        raise InputError(str(exc)) from exc


def canonical(labels) -> list[int]:
    ids = {}
    return [ids.setdefault(x, len(ids)) for x in labels]


def partition(labels: Any, n: int) -> list[int]:
    need(type(labels) is list and len(labels) == n, 'partition size')
    for x in labels:
        integer(x, 0, n - 1)
    need(labels == canonical(labels), 'noncanonical partition')
    return labels


def blocks(labels: list[int]) -> list[list[int]]:
    return [[i for i, x in enumerate(labels) if x == k] for k in dict.fromkeys(labels)]


def value(table: list[int], args, n: int) -> int:
    pos = 0
    for x in args:
        pos = pos * n + x
    return table[pos]


def records(n: int, ops: list[dict], copies: int = 1) -> list[tuple]:
    return [(oi, tuple(copy * n + x for x in xs), copy * n + y)
            for copy in range(copies) for oi, op in enumerate(ops)
            for xs, y in zip(itertools.product(range(n), repeat=op['arity']), op['table'])]


def quotient(n: int, ops: list[dict], theta: list[int]) -> tuple[int, list[dict]]:
    partition(theta, n)
    m = len(set(theta))
    result = []
    for op in ops:
        table = {}
        for xs, y in zip(itertools.product(range(n), repeat=op['arity']), op['table']):
            key, out = tuple(theta[x] for x in xs), theta[y]
            need(key not in table or table[key] == out, 'carrier partition is not a native congruence')
            table[key] = out
        result.append(dict(name=op['name'], arity=op['arity'],
                           table=[table[xs] for xs in itertools.product(range(m), repeat=op['arity'])]))
    return m, result


def kernel_seeds(h: list[int | None]) -> list[tuple[int, int]]:
    first = {}
    pairs = []
    for x, y in enumerate(h):
        if y is not None:
            if y in first:
                pairs.append((first[y], x))
            else:
                first[y] = x
    return pairs


def lift_seeds(theta: list[int], kernels: list[list[int]]) -> list[tuple[int, int]]:
    result = []
    for chi in kernels:
        first = {}
        for a, qa in enumerate(theta):
            key = chi[qa]
            if key in first:
                result.append((first[key], a))
            else:
                first[key] = a
    return result


class DSU:
    """Union mechanics only. Checkers never invoke a saturation procedure."""
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> bool:
        a, b = self.find(a), self.find(b)
        if a == b:
            return False
        self.parent[max(a, b)] = min(a, b)
        return True

    def labels(self) -> list[int]:
        return canonical(self.find(x) for x in range(len(self.parent)))
