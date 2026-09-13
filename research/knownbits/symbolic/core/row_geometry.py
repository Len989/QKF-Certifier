"""Exact concrete gluing of primitive count rows, independent of proof search.

Intervals use [lo, hi). A certificate either gives two incompatible supplied
cells at one index, or a piecewise constant word completing all supplied rows.
Neither width enumeration nor a Boolean/arithmetic solver is used.
"""
import hashlib
import json

KINDS = ('clz', 'clo', 'ctz', 'cto')


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def intervals(width, counts):
    if type(width) is not int or width < 1:
        raise ValueError('positive integer width')
    if not isinstance(counts, dict) or any(k not in KINDS for k in counts):
        raise ValueError('count names')
    result = []
    for kind, count in sorted(counts.items()):
        if type(count) is not int or not 0 <= count <= width:
            raise ValueError('count outside [0,w]')
        bit = int(kind.endswith('o'))
        leading = kind.startswith('cl')
        if count:
            lo, hi = (width - count, width) if leading else (0, count)
            result.append(dict(kind=kind, part='run', lo=lo, hi=hi, bit=bit))
        if count < width:
            stop = width - count - 1 if leading else count
            result.append(dict(kind=kind, part='stop', lo=stop, hi=stop + 1, bit=1 - bit))
    return result


def certify(width, counts):
    rows = intervals(width, counts)
    base = dict(schema='qkf-count-row-gluing-v1', source_hash=digest([width, counts]))
    for i, a in enumerate(rows):
        for j, b in enumerate(rows[:i]):
            if a['bit'] != b['bit'] and max(a['lo'], b['lo']) < min(a['hi'], b['hi']):
                return dict(base, status='incompatible', rows=[j, i], index=max(a['lo'], b['lo']))
    endpoints = sorted({0, width} | {p for r in rows for p in (r['lo'], r['hi'])})
    segments = []
    for lo, hi in zip(endpoints, endpoints[1:]):
        forced = [r['bit'] for r in rows if r['lo'] <= lo < r['hi']]
        bit = forced[0] if forced else 0
        if segments and segments[-1][2] == bit:
            segments[-1][1] = hi
        else:
            segments.append([lo, hi, bit])
    return dict(base, status='realizable', segments=segments)


def verify(width, counts, certificate):
    # Check only the supplied witness, never call the constructor certify().
    rows = intervals(width, counts)
    if certificate.get('schema') != 'qkf-count-row-gluing-v1' or certificate.get('source_hash') != digest([width, counts]):
        raise ValueError('schema/source binding')
    if certificate.get('status') == 'incompatible':
        ids = certificate.get('rows')
        index = certificate.get('index')
        if not isinstance(ids, list) or len(ids) != 2 or any(type(i) is not int or not 0 <= i < len(rows) for i in ids):
            raise ValueError('row references')
        if type(index) is not int:
            raise ValueError('index')
        a, b = (rows[i] for i in ids)
        if a['bit'] == b['bit'] or not (a['lo'] <= index < a['hi'] and b['lo'] <= index < b['hi']):
            raise ValueError('no carrier conflict')
        return dict(status='incompatible', forced_equal_bits=[a['bit'], b['bit']], query_depth=1)
    if certificate.get('status') != 'realizable':
        raise ValueError('status')
    segments = certificate.get('segments')
    if not isinstance(segments, list) or not segments:
        raise ValueError('word segments')
    end = 0
    for segment in segments:
        if not isinstance(segment, list) or len(segment) != 3 or any(type(v) is not int for v in segment):
            raise ValueError('segment syntax')
        lo, hi, bit = segment
        if lo != end or not lo < hi <= width or bit not in (0, 1):
            raise ValueError('segment partition')
        for row in rows:
            if max(lo, row['lo']) < min(hi, row['hi']) and bit != row['bit']:
                raise ValueError('row value not preserved')
        end = hi
    if end != width:
        raise ValueError('incomplete word')
    return dict(status='realizable', segments=len(segments))


def actual_counts(width, segments):
    """Compute end runs directly from a certified segmented word."""
    result = {}
    for kind in KINDS:
        count = 0
        for lo, hi, bit in reversed(segments) if kind.startswith('cl') else segments:
            if bit != int(kind.endswith('o')):
                break
            count += hi - lo
        result[kind] = count
    return result
