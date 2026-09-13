"""Forced observation rows on the protected carrier P({less,equal,greater})."""
import hashlib, json

RELATIONS = (-1, 0, 1)


def require(p, text):
    if not p:
        raise ValueError(text)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',',':')).encode()).hexdigest()


def compare(a,b):
    return (a>b)-(a<b)


def prefix(h,a,b):
    return h or compare(a,b)


def select(guard, optional, relation):
    tag = guard[0]
    if tag == 'optional':
        return bool(optional)
    if tag == 'comparison':
        return relation in guard[1]
    if tag == 'not':
        return not select(guard[1],optional,relation)
    require(tag in {'and','or'} and len(guard)==3, 'source guard IR')
    a = select(guard[1],optional,relation); b = select(guard[2],optional,relation)
    return a and b if tag == 'and' else a or b


def atom(guard, label, source_atom):
    """Native supplied cell, retaining the same unknown higher prefix."""
    a,optional,u,y,suffix = label
    require((a,optional) in {(0,0),(0,1),(1,0)} and u in (0,1)
            and y in range(a,a+optional+1) and suffix in RELATIONS, 'row label')
    result = 0
    for h in RELATIONS:
        through = prefix(h,y,u)
        candidate = prefix(h,1,u) or suffix
        chosen = a | int(select(guard,optional,candidate))
        if through == source_atom and y == chosen:
            result |= 1 << (h+1)
    return result


def labels():
    return [(a,o,u,y,r) for a,o in [(0,0),(0,1),(1,0)] for u in (0,1)
            for y in range(a,a+o+1) for r in RELATIONS]


def replay_row(guard, label, certificate):
    require(set(certificate)=={'label','supplied','steps','table','kernel'}, 'row fields')
    require(certificate['label']==list(label), 'row label binding')
    expected = [[1<<(r+1),atom(guard,label,r)] for r in RELATIONS]
    require(certificate['supplied']==expected, 'native supplied atoms')
    values = dict(expected)
    for step in certificate['steps']:
        require(set(step)=={'operation','left','right','input','output'}, 'row inference fields')
        op=step['operation']; a=step['left']; b=step['right']
        require(op in {'union','intersection'} and a in values and b in values, 'prior row premises')
        source = a|b if op=='union' else a&b
        image = values[a]|values[b] if op=='union' else values[a]&values[b]
        require(step['input']==source and step['output']==image and source not in values, 'forced row inference')
        values[source]=image
    require(set(values)==set(range(8)), 'full forced row domain')
    table = [values[i] for i in range(8)]
    require(certificate['table']==table, 'row completion')
    # A total carrier-protecting completion; ground identities are not imposed
    # on unnamed elements of arbitrary models.
    for a in range(8):
        for b in range(8):
            require(table[a|b]==table[a]|table[b] and table[a&b]==table[a]&table[b], 'row homomorphism')
    groups = [[i for i in range(8) if table[i]==value] for value in sorted(set(table))]
    require(certificate['kernel']==groups, 'row kernel')
    return table


def replay_rows(guard, certificates):
    require(type(certificates) is list and len(certificates)==len(labels()), 'complete native row family')
    # Nonoptional zero bits must remain zero; otherwise the source sweep does
    # not have the fixed-bit carrier used in the universal proof.
    require(not any(select(guard,False,r) for r in RELATIONS), 'source changes a fixed zero bit')
    return {label:replay_row(guard,label,c) for label,c in zip(labels(),certificates)}
