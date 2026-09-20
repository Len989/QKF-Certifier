"""Versioned request boundary. Operational options never become semantic premises."""
import hashlib
import json

SCHEMA = 'qkf-semantic-request-v1'
PROOF = 'qkf-semantic-control-proof-v1'
PROFILE = 'modular-lsb-signed-word-predicates-v1'
GUARANTEES = ('consumer_sufficient', 'exact_source_interface', 'minimal_source_interface')
MAX_BYTES = 5_000_000


def need(test, message):
    if not test:
        raise ValueError(message)


def integer(value, low, high):
    need(type(value) is int and low <= value <= high, 'integer within declared range required')
    return value


def canonical(value):
    """Bounded plain JSON, with pre-serialization depth, occurrence and integer limits."""
    active = set()
    count = 0
    def visit(x, depth):
        nonlocal count
        count += 1
        need(count <= 300_000 and depth <= 96, 'JSON structural budget')
        t = type(x)
        if t is int:
            need(x.bit_length() <= 8192, 'integer bit budget')
        elif t is str:
            need(len(x) <= MAX_BYTES, 'string budget')
        elif t not in (bool, type(None)):
            need(t in (dict, list) and id(x) not in active, 'acyclic plain JSON; no float or code')
            active.add(id(x))
            if t is dict:
                need(all(type(k) is str for k in x), 'string JSON keys')
                for k, v in x.items():
                    visit(k, depth + 1)
                    visit(v, depth + 1)
            else:
                for v in x:
                    visit(v, depth + 1)
            active.remove(id(x))
    visit(value, 0)
    text = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    need(len(text.encode()) <= MAX_BYTES, 'JSON byte budget')
    return text


def snapshot(value):
    return json.loads(canonical(value))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def load_json(path):
    with open(path, 'rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    need(len(raw) <= MAX_BYTES, 'JSON byte budget')
    def pairs(items):
        result = {}
        for k, v in items:
            need(k not in result, 'duplicate JSON key')
            result[k] = v
        return result
    def number(s):
        need(len(s) <= 2500, 'integer token budget')
        return int(s)
    def reject(s):
        raise ValueError('noninteger JSON numeric token: ' + s[:30])
    return snapshot(json.loads(raw, object_pairs_hook=pairs, parse_int=number,
                               parse_float=reject, parse_constant=reject))


def save_json(path, value):
    text = canonical(value)
    with open(path, 'x', encoding='utf-8', newline='\n') as stream:
        stream.write(text + '\n')


def request(raw):
    r = snapshot(raw)
    need(type(r) is dict and set(r) == {'schema', 'source', 'selection', 'profile',
        'conditions', 'consumer', 'guarantee', 'budget', 'strategy', 'search'}, 'request fields')
    need(r['schema'] == SCHEMA and r['profile'] == PROFILE, 'request schema/profile')
    need(type(r['source']) is str and len(r['source'].encode('utf-8')) <= 2_000_000, 'source text')
    need(type(r['consumer']) is dict and set(r['consumer']) == {'kind', 'target'}
         and r['consumer']['kind'] == 'signed_target', 'independent signed consumer')
    from research.signed_targets.common import prepare
    from research.signed_coverage.targets import budgets
    from research.signed_witness.common import budgets as search_budgets
    _, selection = prepare(r['consumer']['target'])
    need(canonical(selection) == canonical(r['selection']), 'consumer/source selection mismatch')
    need(r['guarantee'] in GUARANTEES, 'explicit guarantee level')
    need(r['strategy'] in ('covered', 'witness_then_covered'), 'explicit control strategy')
    need(type(r['conditions']) is list and len(r['conditions']) <= 16, 'condition list')
    # Conditions are syntactically validated, but nonempty assumptions are NOT
    # implemented by this baseline. The runner returns unresolved, never ignores them.
    for condition in r['conditions']:
        t = snapshot(r['consumer']['target'])
        t['goal'] = condition
        prepare(t)
    b = r['budget']
    need(type(b) is dict and set(b) == {'max_work', 'max_attempts', 'backend'}, 'budget fields')
    integer(b['max_work'], 0, 20_000_000)
    integer(b['max_attempts'], 0, 64)
    budgets(b['backend'])
    search_budgets(r['search'])
    return r


def make_request(source, target, *, strategy='covered', conditions=None,
                 guarantee='consumer_sufficient', max_work=2_000_000, max_attempts=2,
                 backend=None, search=None):
    from research.signed_targets.common import prepare
    _, selection = prepare(target)
    return request(dict(schema=SCHEMA, source=source, selection=selection, profile=PROFILE,
        conditions=[] if conditions is None else conditions,
        consumer={'kind': 'signed_target', 'target': target}, guarantee=guarantee,
        strategy=strategy, budget={'max_work': max_work, 'max_attempts': max_attempts,
                                   'backend': {} if backend is None else backend},
        search={'max_width': 8, 'max_evaluations': 510} if search is None else search))
