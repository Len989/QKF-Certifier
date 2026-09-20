"""Bounded plain-JSON DAG transport. Earlier references are data, never code.

Sharing is syntactic, not semantic equality. Expansion budgets are computed
before allocating decoded containers; repeated references cannot hide a bomb.
"""
import json
from research.observations.model import integer, require
from research.signed_context.io import freeze, thaw

SCHEMA = 'qkf-json-proof-dag-v1'
MAX_NODES = 100000
MAX_DEPTH = 128
MAX_EXPANDED = 5000000


def pack(value):
    value = thaw(freeze(value))
    nodes, intern = [], {}
    def visit(obj, depth):
        require(depth <= MAX_DEPTH, 'DAG depth budget')
        if type(obj) is dict:
            record = ['d', [[k, visit(v, depth+1)] for k, v in sorted(obj.items())]]
        elif type(obj) is list:
            record = ['l', [visit(v, depth+1) for v in obj]]
        else:
            record = ['v', obj]
        key = freeze(record)  # Distinguishes Boolean and integer payloads.
        if key not in intern:
            require(len(nodes) < MAX_NODES, 'DAG node budget')
            intern[key] = len(nodes)
            nodes.append(record)
        return intern[key]
    root = visit(value, 0)
    packet = {'schema': SCHEMA, 'nodes': nodes, 'root': root}
    unpack(packet)  # Apply exactly the decoder's depth/expanded-size limits.
    return packet


def unpack(packet):
    require(type(packet) is dict and set(packet) == {'schema', 'nodes', 'root'}
            and packet['schema'] == SCHEMA, 'DAG envelope')
    nodes = packet['nodes']
    require(type(nodes) is list and 0 < len(nodes) <= MAX_NODES, 'DAG node budget')
    require(integer(packet['root'], 0, len(nodes)-1), 'DAG root')
    sizes, depths, refs, seen = [], [], [], set()
    wire = 0
    for i, row in enumerate(nodes):
        require(type(row) is list and len(row) == 2 and type(row[0]) is str, 'DAG node shape')
        kind, body = row
        children = []
        if kind == 'v':
            require(type(body) in (str, bool, int, type(None)), 'DAG scalar type; floats are not proof data')
            if type(body) is int: require(body.bit_length() <= 20000, 'DAG integer budget')
            size, depth = len(json.dumps(body, allow_nan=False).encode()), 0
        elif kind in {'l', 'd'}:
            require(type(body) is list and len(body) <= MAX_NODES, 'DAG child list')
            if kind == 'l':
                children = body
                overhead = 2 + max(0, len(body)-1)
            else:
                keys = []
                overhead = 2 + max(0, len(body)-1)
                for pair in body:
                    require(type(pair) is list and len(pair) == 2 and type(pair[0]) is str,
                            'DAG object pair')
                    keys.append(pair[0]); children.append(pair[1])
                    overhead += len(json.dumps(pair[0]).encode()) + 1
                require(keys == sorted(set(keys)), 'DAG keys unique and sorted')
            require(all(integer(r, 0, i-1) for r in children), 'DAG references must be strictly earlier')
            size = overhead + sum(sizes[r] for r in children)
            depth = 1 + max((depths[r] for r in children), default=0)
        else:
            raise ValueError('unknown DAG node kind')
        require(size <= MAX_EXPANDED and depth <= MAX_DEPTH, 'DAG expansion/depth budget')
        key = freeze(row)
        wire += len(key.encode())
        require(wire <= MAX_EXPANDED, 'DAG wire budget')
        require(key not in seen, 'duplicate DAG record')
        seen.add(key); sizes.append(size); depths.append(depth); refs.append(children)
    reachable, pending = set(), [packet['root']]
    while pending:
        i = pending.pop()
        if i not in reachable:
            reachable.add(i); pending.extend(refs[i])
    require(len(reachable) == len(nodes), 'unreachable DAG records')
    values = []
    for kind, body in nodes:
        values.append(body if kind == 'v' else
                      [values[r] for r in body] if kind == 'l' else
                      {k: values[r] for k, r in body})
    # Detach repeated references at the public boundary; finite size checked above.
    return thaw(freeze(values[packet['root']]))
