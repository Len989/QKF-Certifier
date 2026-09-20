"""Strict, typed, topological input DAG shared by producer and checker.

The input declares a finite ground presentation, never universal axioms or a
program semantics. Unused signature symbols/sorts are legal; unused DAG nodes
are not: the node set is exactly Sub(E) union Sub(O).
"""

from dataclasses import dataclass
import hashlib
import json
import re

INPUT_SCHEMA = 'qkf-ground-query-input-v1'
PROOF_SCHEMA = 'qkf-ground-query-certificate-v1'
MAX_NODES = 20000
MAX_DEPTH = 128
MAX_STEPS = 200000
MAX_BYTES = 64 * 1024 * 1024
MAX_OBJECTS = 4_000_000
MAX_ARITY = 64


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fields(value, keys, where):
    require(type(value) is dict and set(value) == set(keys), where + ': fields')


def index(value, size, where):
    require(type(value) is int and 0 <= value < size, where + ': index')
    return value


def canonical(value):
    """Bounded plain JSON; do not call arbitrary object encoders or accept NaN."""
    active, count = set(), 0
    def visit(x, depth):
        nonlocal count
        count += 1
        require(count <= MAX_OBJECTS and depth <= 64, 'JSON structural budget')
        t = type(x)
        if t is int:
            require(x.bit_length() <= 256, 'JSON integer budget')
        elif t is str:
            require(len(x) <= MAX_BYTES, 'JSON string budget')
        elif t not in (bool, type(None)):
            require(t in (dict, list) and id(x) not in active, 'acyclic plain JSON required')
            active.add(id(x))
            if t is dict:
                require(all(type(k) is str for k in x), 'JSON string keys required')
                for k, v in x.items():
                    visit(k, depth + 1)
                    visit(v, depth + 1)
            else:
                for v in x:
                    visit(v, depth + 1)
            active.remove(id(x))
    visit(value, 0)
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                     allow_nan=False).encode()
    require(len(raw) <= MAX_BYTES, 'JSON byte budget')
    return raw


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def load_json(path):
    """Reject ambiguous JSON objects rather than silently accepting the last key."""
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key: ' + key)
            result[key] = value
        return result
    def reject(token):
        raise ValueError('noninteger JSON numeric token: ' + token[:30])
    with open(path, 'rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, 'JSON byte budget')
    return json.loads(canonical(json.loads(raw, object_pairs_hook=pairs,
                                          parse_float=reject, parse_constant=reject)))


def save_json(path, value):
    raw = canonical(value)
    with open(path, 'xb') as stream:
        stream.write(raw + b'\n')


@dataclass(frozen=True)
class Input:
    sorts: tuple
    signature: dict
    nodes: tuple
    node_sorts: tuple
    depths: tuple
    equations: tuple
    queries: tuple
    horizon: int
    identity: str


def parse(value):
    value = json.loads(canonical(value))
    fields(value, ('schema', 'sorts', 'signature', 'nodes', 'equations', 'queries'), 'input')
    require(value['schema'] == INPUT_SCHEMA, 'input schema')
    sorts = value['sorts']
    require(type(sorts) is list and 0 < len(sorts) <= MAX_NODES, 'nonempty sort declaration')
    require(all(type(s) is str and re.fullmatch(r'[A-Za-z0-9_:.+\-]{1,128}', s) for s in sorts), 'sort name')
    require(len(set(sorts)) == len(sorts), 'duplicate sort')
    sig = value['signature']
    require(type(sig) is dict and len(sig) <= MAX_NODES, 'signature')
    for name, spec in sig.items():
        require(type(name) is str and re.fullmatch(r'[A-Za-z0-9_:.+\-]{1,128}', name), 'symbol name')
        fields(spec, ('args', 'result'), 'symbol')
        require(type(spec['args']) is list and len(spec['args']) <= MAX_ARITY
                and all(type(s) is str and s in sorts for s in spec['args']), 'argument sorts')
        require(type(spec['result']) is str and spec['result'] in sorts, 'result sort')
    nodes = value['nodes']
    require(type(nodes) is list and len(nodes) <= MAX_NODES, 'node budget')
    depths, types, frozen, seen = [], [], [], set()
    for i, node in enumerate(nodes):
        fields(node, ('op', 'args'), 'node')
        name, args = node['op'], node['args']
        require(type(name) is str and name in sig, 'unknown symbol')
        require(type(args) is list and len(args) == len(sig[name]['args']), 'node arity')
        for arg, sort in zip(args, sig[name]['args']):
            index(arg, i, 'topological argument')
            require(types[arg] == sort, 'ill-sorted argument')
        key = (name, tuple(args))
        require(key not in seen, 'duplicate DAG term')
        seen.add(key)
        d = 1 + max(depths[a] for a in args) if args else 0
        require(d <= MAX_DEPTH, 'term depth budget')
        depths.append(d)
        types.append(sig[name]['result'])
        frozen.append(key)
    collections = []
    roots = set()
    for label in ('equations', 'queries'):
        pairs = value[label]
        require(type(pairs) is list and len(pairs) <= MAX_STEPS, label + ' budget')
        checked = []
        for pair in pairs:
            require(type(pair) is list and len(pair) == 2, label + ' pair')
            a, b = (index(i, len(nodes), label) for i in pair)
            require(types[a] == types[b], 'ill-sorted equality')
            roots.update(pair)
            checked.append((a, b))
        collections.append(tuple(checked))
    needed, stack = set(), list(roots)
    while stack:
        i = stack.pop()
        if i not in needed:
            needed.add(i)
            stack.extend(frozen[i][1])
    require(len(needed) == len(nodes), 'DAG contains terms outside Sub(E) union Sub(O)')
    return Input(tuple(sorts), sig, tuple(frozen), tuple(types), tuple(depths),
                 *collections, max(depths, default=0), digest(value))
