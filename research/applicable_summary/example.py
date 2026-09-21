"""One executable SDK example from the repository root."""
import json
from . import build, check
from .contract import signed_request

SOURCE = '''class Demo { static boolean f(long x) {
    return (x<0) && (((x+x)&1)==0);
} }'''


def target(formula):
    return dict(schema='qkf-target-v2', kind='signed_boolean_predicate',
                source=dict(entry=dict(**{'class': 'Demo'}, method='f'), word_type='long'), goal=formula)


def run():
    req = signed_request(target(['negative']), guards=[['popcount_le', 1]])
    packet, result, work = build(SOURCE, req)
    if result['status'] != 'certified':
        raise RuntimeError(result)
    summary = check(SOURCE, req, packet)
    outputs = [summary.apply(v, width=8) for v in (0, 1, 128)]
    consumer = signed_request(target(['not', ['nonnegative']]), guards=[['popcount_le', 1]])
    assessed = summary.assess(consumer)
    if outputs != [False, False, True] or assessed['status'] != 'certified':
        raise RuntimeError('example result')
    return dict(status=result['status'], outputs=outputs, new_consumer=assessed,
                selected_route=work['backend']['route'], explanation=summary.explain(consumer=consumer))


if __name__ == '__main__':
    print(json.dumps(run(), sort_keys=True))
