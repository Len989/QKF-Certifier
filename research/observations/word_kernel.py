"""Replay symbolic integer pullbacks and finite actions extracted from Java.

Intervals range over all integers, not a sampled width. The trusted arithmetic
rule is append(a)-append(b) = 2*d+a-b. No observation search is run here.
"""
from .context_model import ContextModel, SCHEMA as CONTEXT_SCHEMA
from .java_words import read_source
from .model import digest, integer, require

SCHEMA = 'qkf-integer-word-observation-v1'


def seed_cuts(test):
    op, k = test['op'], test['offset']
    if op in {'<=', '>'}: return [k]
    if op in {'<', '>='}: return [k - 1]
    return [k - 1, k]


def deltas(ir, lower_only=False):
    values = set()
    for c in ir['columns']:
        a, _, u, y = map(int, c['symbol'])
        values.add(a - u)
        if not lower_only: values.update((y - u, 1 - u))
    return sorted(values)


def intervals(cuts):
    return [{'lower': None if i == 0 else cuts[i - 1] + 1,
             'upper': cuts[i] if i < len(cuts) else None} for i in range(len(cuts) + 1)]


def locate(parts, value):
    return next(i for i, p in enumerate(parts)
                if (p['lower'] is None or p['lower'] <= value) and (p['upper'] is None or value <= p['upper']))


def truth(part, test):
    lo, hi = part['lower'], part['upper']; op, k = test['op'], test['offset']
    if op in {'==', '!='}:
        if lo == hi == k: value = True
        elif (hi is not None and hi < k) or (lo is not None and lo > k): value = False
        else: raise ValueError('word predicate cuts an observation interval')
        return value if op == '==' else not value
    threshold = k - 1 if op in {'<', '>='} else k
    if hi is not None and hi <= threshold: value = True
    elif lo is not None and lo > threshold: value = False
    else: raise ValueError('word predicate cuts an observation interval')
    return value if op in {'<', '<='} else not value


def decision(guard, optional, answers):
    tag = guard[0]
    if tag == 'optional': return optional
    if tag == 'test': return answers[guard[1]]
    if tag == 'not': return not decision(guard[1], optional, answers)
    left = decision(guard[1], optional, answers); right = decision(guard[2], optional, answers)
    return left and right if tag == 'and' else left or right


def check_word(source, cert):
    ir = read_source(source)
    require(type(cert) is dict and set(cert) == {
        'schema', 'source_ir', 'questions', 'intervals', 'actions', 'origin', 'consumer', 'monoid', 'composition'
    }, 'word certificate fields')
    require(cert['schema'] == SCHEMA and digest(cert['source_ir']) == digest(ir), 'word proof source binding')
    ds = deltas(ir); lower_ds = deltas(ir, True)
    ps = cert['questions']; require(type(ps) is list and 0 < len(ps) <= 7, 'word question budget')
    cuts = []
    for i, p in enumerate(ps):
        require(type(p) is dict and type(p.get('cut')) is int and p.get('kind') in {'seed', 'pullback'},
                'word question derivation')
        t = p['cut']; require(t not in cuts, 'distinct integer cuts')
        if p['kind'] == 'seed':
            require(set(p) == {'kind', 'cut', 'test'} and integer(p['test'], 0, len(ir['tests']) - 1)
                    and t in seed_cuts(ir['tests'][p['test']]), 'native comparison question')
        else:
            require(set(p) == {'kind', 'cut', 'parent', 'delta'} and integer(p['parent'], 0, i - 1)
                    and type(p['delta']) is int and p['delta'] in ds, 'word pullback premises')
            require(t == (cuts[p['parent']] - p['delta']) // 2, 'exact integer affine pullback')
        cuts.append(t)
    require(all(t in cuts for test in ir['tests'] for t in seed_cuts(test)), 'all native questions represented')
    require(all((t - d) // 2 in cuts for t in cuts for d in ds), 'integer observation closure')
    parts = cert['intervals']; expected = intervals(sorted(cuts))
    require(type(parts) is list and all(type(p) is dict and set(p) == {'lower', 'upper'}
            and all(v is None or type(v) is int for v in p.values()) for p in parts)
            and parts == expected, 'exact partition of the integers')
    n = len(parts); rows = cert['actions']; actions = {}
    require(type(rows) is list and len(rows) == len(ds), 'all bit append actions')
    for row in rows:
        require(type(row) is dict and set(row) == {'delta', 'targets'} and type(row['delta']) is int
                and row['delta'] in ds and row['delta'] not in actions, 'unique append action')
        targets = row['targets']; d = row['delta']
        require(type(targets) is list and len(targets) == n and all(integer(j, 0, n - 1) for j in targets),
                'append action carrier')
        for p, j in zip(parts, targets):
            q = parts[j]
            lo = None if p['lower'] is None else 2 * p['lower'] + d
            hi = None if p['upper'] is None else 2 * p['upper'] + d
            require(q['lower'] is None or (lo is not None and q['lower'] <= lo), 'entire lower affine image')
            require(q['upper'] is None or (hi is not None and hi <= q['upper']), 'entire upper affine image')
        actions[d] = targets
    require(integer(cert['origin'], 0, n - 1) and cert['origin'] == locate(parts, 0), 'empty-word observation')
    consumers = cert['consumer']
    require(type(consumers) is list and len(consumers) == n and all(type(r) is list
            and len(r) == len(ir['tests']) and all(type(v) is bool for v in r) for r in consumers), 'consumer answers')
    require(consumers == [[truth(p, t) for t in ir['tests']] for p in parts], 'protected word predicate labels')
    monoid = cert['monoid']; require(type(monoid) is list and 0 < len(monoid) <= 16, 'finite suffix action budget')
    maps = []
    for i, node in enumerate(monoid):
        require(type(node) is dict and set(node) == {'map', 'parent'} and type(node['map']) is list
                and len(node['map']) == n and all(integer(j, 0, n - 1) for j in node['map']), 'suffix action map')
        f = node['map']; require(f not in maps, 'distinct suffix actions')
        p = node['parent']
        if i == 0:
            require(p is None and f == list(range(n)), 'empty suffix is identity')
        else:
            require(type(p) is dict and set(p) == {'state', 'delta'} and integer(p['state'], 0, i - 1)
                    and type(p['delta']) is int and p['delta'] in lower_ds, 'suffix action derivation')
            require(f == [maps[p['state']][j] for j in actions[p['delta']]], 'prepend action composition')
        maps.append(f)
    composition = cert['composition']; require(type(composition) is list and len(composition) == len(maps) * len(lower_ds),
                                              'closed suffix action family')
    seen = set()
    for edge in composition:
        require(type(edge) is dict and set(edge) == {'state', 'delta', 'next'}
                and integer(edge['state'], 0, len(maps) - 1) and integer(edge['next'], 0, len(maps) - 1)
                and type(edge['delta']) is int and edge['delta'] in lower_ds, 'suffix composition cell')
        key = edge['state'], edge['delta']; require(key not in seen, 'unique suffix composition'); seen.add(key)
        require(maps[edge['next']] == [maps[edge['state']][j] for j in actions[edge['delta']]], 'suffix closure equation')
    require(all(not decision(ir['guard'], False, answer) for answer in consumers), 'source guard must preserve fixed bits')
    return {'status': 'certified', 'integer_cuts': sorted(cuts), 'context_values': n, 'suffix_actions': len(maps),
            'source_tests': ir['tests'], 'append_deltas': ds,
            'scope': 'exact integer pullbacks and word-action composition for the restricted unsigned source profile'}


def compiled_model(source, cert):
    check_word(source, cert)
    ir = cert['source_ir']; n = len(cert['intervals'])
    qs = [f'q{i:02d}' for i in range(n)]; ms = [f'm{i:02d}' for i in range(len(cert['monoid']))]
    actions = {r['delta']: r['targets'] for r in cert['actions']}
    composition = {(r['state'], r['delta']): r['next'] for r in cert['composition']}
    rows = []
    for i, node in enumerate(cert['monoid']):
        f = node['map']
        for col in ir['columns']:
            a, o, u, y = map(int, col['symbol']); edges = []
            for h in range(n):
                trial = f[actions[1 - u][h]]
                selected = decision(ir['guard'], bool(o), cert['consumer'][trial])
                if (a | int(selected)) == y:
                    edges.append([qs[h], qs[actions[y - u][h]]])
            rows.append({'control': ms[i], 'symbol': col['symbol'],
                         'next_control': ms[composition[i, a - u]], 'edges': edges})
    return ContextModel({'schema': CONTEXT_SCHEMA, 'contexts': qs, 'controls': ms,
                         'alphabet': [c['symbol'] for c in ir['columns']], 'initial_control': ms[0],
                         'bottom': qs, 'boundary': qs[cert['origin']], 'rows': rows,
                         'binding': {'adapter': 'source-derived-integer-word-actions-v1',
                                     'source_sha256': ir['source_sha256'], 'word_certificate_sha256': digest(cert),
                                     'source_profile': ir['profile']}}).data
