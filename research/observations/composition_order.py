"""Complete weak-order checking of the wrapper, using already verified lemmas.

A weak order is a rank assignment to every input, call result and a universally
chosen legal competitor. Ranks denote ONLY order/equality, never bit patterns.
Membership is separate provenance, transferred by equality and checked calls.
Contract facts are applied only after that call's entry obligations hold. When
a later result becomes known legal, earlier universal contracts are instantiated
again on it. This is the floor-at-successor handoff needed to exclude t < bound.
"""
from functools import lru_cache

from .composition_program import INPUTS, compare, inspect
from .model import require

MAX_ORDERS = 4683  # ordered Bell number for six labels; a structural limit


@lru_cache(maxsize=4)
def weak_orders(size):
    """Every total preorder, once: insert the last label in a block or a gap."""
    require(type(size) is int and 1 <= size <= 6, 'weak-order label budget')
    partitions = [((0,),)]
    for label in range(1, size):
        following = []
        for blocks in partitions:
            for i in range(len(blocks)):
                following.append(blocks[:i] + (blocks[i] + (label,),) + blocks[i + 1:])
            for i in range(len(blocks) + 1):
                following.append(blocks[:i] + ((label,),) + blocks[i:])
        partitions = following
    result = []
    for blocks in partitions:
        ranks = [0] * size
        for i, block in enumerate(blocks):
            for label in block:
                ranks[label] = i
        result.append(tuple(ranks))
    return tuple(sorted(result))


def domain_orders(program):
    names = inspect(program)['names']
    result = []
    for ranks in weak_orders(len(names)):
        r = dict(zip(names, ranks))
        if r['must'] <= r['alternative'] <= r['may']:
            result.append(ranks)
    return names, tuple(result)


def evaluate(program, names, ranks):
    """One finite proof case; gap means insufficient proof, not a concrete bug."""
    r = dict(zip(names, ranks))
    live = set(INPUTS) | {'alternative'}
    legal = {'must', 'may', 'alternative'}
    floors, successors, trace = [], [], []
    node, path = program['entry'], 'entry'

    def refresh():
        # Equality of unsigned word values is enough to transfer bit membership.
        known_ranks = {r[k] for k in legal}
        legal.update(k for k in live if r[k] in known_ranks)

    def consistent():
        refresh()
        for output, bound in floors:
            if not r['must'] <= r[output] <= r['may'] or r[output] > r[bound]:
                return False
            if any(r[x] <= r[bound] and r[x] > r[output] for x in legal):
                return False
        for output, seed in successors:
            if not r['must'] <= r[output] <= r['may']:
                return False
            if r[seed] == r['may']:
                if r[output] != r['must']:
                    return False
            elif r[output] <= r[seed]:
                return False
            if any(r[x] > r[seed] and r[output] > r[x] for x in legal):
                return False
        return True

    def gap(reason):
        return {'outcome': 'gap', 'path': path, 'reason': reason, 'trace': trace}

    while True:
        refresh()
        op = node['op']
        if op == 'if':
            chosen = 'yes' if compare(node['test'], r) else 'no'
            trace.append([path, chosen])
            node, path = node[chosen], path + '.' + chosen
        elif op == 'call':
            role, args, output = node['role'], node['args'], node['bind']
            if r[args['must']] != r['must'] or r[args['may']] != r['may']:
                return gap('shared_mask_identity_not_established')
            if role == 'descending':
                if r[args['seed']] != r['must']:
                    return gap('floor_seed_is_not_mask_minimum')
                if r[args['seed']] > r[args['bound']]:
                    return gap('floor_nonempty_precondition_not_established')
                floors.append((output, args['bound']))
            else:
                if args['seed'] not in legal:
                    return gap('successor_entry_membership_not_established')
                successors.append((output, args['seed']))
            live.add(output)
            legal.add(output)
            trace.append([path, role, output])
            if not consistent():
                return {'outcome': 'contract_eliminated', 'path': path, 'trace': trace}
            node, path = node['then'], path + '.then'
        elif op == 'empty':
            if r['bound'] <= r['may']:
                return gap('empty_not_established')
            return {'outcome': 'empty', 'path': path, 'trace': trace}
        else:
            word = node['word']
            if word not in legal:
                return gap('result_membership_not_established')
            if r[word] < r['bound']:
                return gap('result_below_bound')
            if r['bound'] <= r['alternative'] < r[word]:
                return gap('result_not_minimal')
            return {'outcome': 'value', 'path': path, 'word': word, 'trace': trace}
