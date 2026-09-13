#!/usr/bin/env python3
"""Construct a uniform ground proof and test nontrivial lattice saturation."""
from collections import deque
import json
from pathlib import Path
import time
from core.ground_checker import digest, tree, depth, verify, verify_model
ROOT = Path(__file__).resolve().parent


def obligation():
    row = lambda x: ['row', x]
    meet = lambda x, y: ['meet', x, y]
    return dict(schema='qkf-ground-obligation-v1', constants=['zero', 'U', 'a'],
                signature=dict(row=1, meet=2), equations=[
                    [row('U'), 'zero'], [row('zero'), 'zero'],
                    [meet('a', 'U'), 'a'], [meet('a', 'zero'), 'zero'],
                    [row(meet('a', 'U')), meet(row('a'), row('U'))],
                    [row(meet('a', 'zero')), meet(row('a'), row('zero'))]],
                query=[row('a'), 'zero'],
                interpretation='a is any submask of U; zero is the zero word; row preserves AND on named inputs. No universal law on unnamed row values is assumed.')


def produce(source):
    nodes = []
    def emit(kind, **fields): nodes.append(dict(kind=kind, **fields)); return len(nodes)-1
    inputs = [emit('input', equation=i) for i in range(6)]
    reflected = emit('sym', premise=inputs[1])
    same_row = emit('trans', left=inputs[0], right=reflected)
    fixed = emit('refl', term=['row', 'a'])
    context = emit('congr', operation='meet', premises=[fixed, same_row])
    source_equal = emit('congr', operation='row', premises=[inputs[2]])
    left_start = emit('sym', premise=source_equal)
    left_form = emit('trans', left=left_start, right=inputs[4])
    replace = emit('trans', left=left_form, right=context)
    unfold = emit('sym', premise=inputs[5])
    simplify = emit('congr', operation='row', premises=[inputs[3]])
    step = emit('trans', left=replace, right=unfold)
    step = emit('trans', left=step, right=simplify)
    root = emit('trans', left=step, right=inputs[1])
    return dict(schema='qkf-ground-dag-v1', source_hash=digest(source), nodes=nodes, root=root)


def lower_model(source, horizon):
    terms = set()
    def add(term):
        term = tree(term)
        if depth(term) <= horizon: terms.add(term)
        if isinstance(term, tuple):
            for child in term[1:]: add(child)
    for equation in source['equations']+[source['query']]:
        for term in equation: add(term)
    terms = sorted(terms, key=repr); parent = {t:t for t in terms}
    def find(t):
        if parent[t] != t: parent[t] = find(parent[t])
        return parent[t]
    def merge(a, b):
        a, b = find(a), find(b)
        if a == b: return False
        parent[b] = a; return True
    for a, b in source['equations']:
        a, b = tree(a), tree(b)
        if max(depth(a), depth(b)) <= horizon: merge(a, b)
    changed = True
    while changed:
        changed = False; signatures = {}
        for term in terms:
            if isinstance(term, tuple):
                signature = (term[0], *(find(child) for child in term[1:]))
                if signature in signatures: changed |= merge(term, signatures[signature])
                else: signatures[signature] = term
    classes = {term:i for i, term in enumerate(sorted({find(t) for t in terms}, key=repr))}
    value = lambda term: classes[find(term)]
    tables = {op:{} for op in source['signature']}
    for term in terms:
        if isinstance(term, tuple): tables[term[0]][','.join(str(value(child)) for child in term[1:])] = value(term)
    return dict(size=len(classes), constants={c:value(c) for c in source['constants']}, operations=tables, default=0)


def generated_congruence(width, mask):
    """Generic congruence closure of 0~mask under finite AND/OR tables."""
    size = 1 << width; parent = list(range(size)); work = deque()
    def find(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def merge(a, b):
        ra, rb = find(a), find(b)
        if ra != rb: parent[rb] = ra; work.append((a, b))
    merge(0, mask); contexts = 0
    while work:
        a, b = work.popleft()
        for c in range(size):
            merge(a & c, b & c); merge(a | c, b | c); contexts += 2
    return [find(x) for x in range(size)], contexts


def main():
    start = time.perf_counter(); source = obligation(); certificate = produce(source)
    proof_result = verify(source, certificate)
    model = lower_model(source, 1); lower_result = verify_model(source, model, 1)
    masks = pairs = contexts = 0; records = []
    for width in range(1, 7):
        size = 1 << width
        for mask in range(size):
            classes, work = generated_congruence(width, mask); contexts += work; masks += 1
            for a in range(size):
                for b in range(size):
                    assert (classes[a] == classes[b]) == ((a & ~mask) == (b & ~mask)); pairs += 1
            forced = [a for a in range(size) if classes[a] == classes[0]]
            assert forced == [a for a in range(size) if (a & ~mask) == 0]
            assert len(forced) == 1 << mask.bit_count()
        records.append(dict(width=width, masks=size))
    # Concrete separation outside the saturated domain: the projected row
    # is a named-carrier lattice endomorphism satisfying both supplied cells.
    outside_examples = []
    for width, mask, a in [(3,3,4), (4,5,2)]:
        row = lambda x:x & ~mask
        size = 1 << width
        assert row(0) == row(mask) == 0 and row(a) != 0
        for x in range(size):
            for y in range(size):
                assert row(x & y) == (row(x) & row(y))
                assert row(x | y) == (row(x) | row(y))
        outside_examples.append(dict(width=width, mask=mask, input=a, output=row(a)))
    report = dict(status='passed', proof=proof_result, lower_horizon=lower_result,
                  widths=records, masks=masks, kernel_pairs=pairs, closure_contexts=contexts,
                  outside_domain_models=outside_examples, seconds=time.perf_counter()-start,
                  scope='Uniform proof from an explicit ground presentation, with a separately stated native-word bridge; finite generic closure validates the kernel formula.')
    for name, data in [('obligation', source), ('certificate', certificate), ('lower_model', model), ('validation', report)]:
        path = ROOT/'results/kernel_saturation'/(name+'.json'); path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__': main()
