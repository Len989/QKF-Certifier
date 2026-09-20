"""Fixed native-candidate policy shared verbatim by query and direct control."""
from .encoding import Graph
from .rules import (mask_implication, parity_evidence, input_bridge, local_rhs,
                    guard_truth, check_fact)


def collect(ctx, audit):
    g = Graph(ctx)
    roots = (g.source(), g.target())
    facts, equations, present, replacements = [], [], set(), {}

    def add(value):
        if value is None:
            return
        fact, pair = value
        a, b = pair
        if a == b or pair in present:
            audit.counts['duplicate_or_reflexive_facts'] += 1
            return
        facts.append(fact)
        equations.append(pair)
        present.add(pair)
        replacements[a] = b
        audit.counts['emitted_native_facts'] += 1

    def attempt(candidate, derive):
        add(audit.fact(candidate, derive))

    def native(fact, fn):
        pair = fn()
        return (fact, pair) if pair is not None else None

    for a in range(len(ctx.ir['atoms'])):
        fact = {'rule': 'input-bridge', 'atom': a}
        attempt(fact, lambda f=fact, a=a: native(f, lambda: input_bridge(ctx, g, a)))
        for b in range(len(ctx.ir['atoms'])):
            fact = {'rule': 'eq-mask', 'antecedent': a, 'consequent': b}
            attempt(fact, lambda f=fact, a=a, b=b: native(f, lambda: mask_implication(ctx, g, a, b)))
    for i in range(len(ctx.ir['nodes'])):
        def bit_attempt(i=i):
            rows = parity_evidence(ctx, i)
            if rows is None:
                return None
            fact = {'rule': 'low-bit', 'masked_node': i, 'rows': rows}
            return fact, check_fact(ctx, g, fact)
        attempt({'rule': 'low-bit', 'masked_node': i}, bit_attempt)
    def zero_attempt():
        if ctx.domain and all(c == 0 for c, _ in ctx.domain):
            fact = {'rule': 'guard-zero'}
            return fact, check_fact(ctx, g, fact)
        return None
    attempt({'rule': 'guard-zero'}, zero_attempt)

    done, active = {}, set()
    def normalize(i):
        if i in done:
            return done[i]
        if i in active:
            raise ValueError('cyclic native normalization policy')
        active.add(i)
        if i in replacements:
            result = normalize(replacements[i])
        else:
            op, args = g.row(i)
            current = g.node(op, *(normalize(a) for a in args))
            if current in replacements:
                result = normalize(replacements[current])
            else:
                def local():
                    rhs = local_rhs(ctx, g, current)
                    if rhs is None:
                        return None
                    law, target = rhs
                    return {'rule': 'local', 'term': current, 'law': law}, (current, target)
                attempt({'rule': 'local', 'term': current}, local)
                if current not in replacements:
                    fact = {'rule': 'guard-truth', 'term': current}
                    attempt(fact, lambda: native(fact, lambda: guard_truth(ctx, g, current)))
                result = normalize(replacements[current]) if current in replacements else current
        active.remove(i)
        done[i] = result
        return result

    # These proposed normal forms only guide term instantiation. A positive
    # verdict still requires a chronological ground proof checked independently.
    normal = tuple(normalize(i) for i in roots)
    ground, facts = g.finish(equations, roots, facts)
    audit.counts['compiled_word_nodes'] = len(ctx.ir['nodes'])
    audit.counts['compiled_source_atoms'] = len(ctx.ir['atoms'])
    audit.counts['ground_input_nodes'] = len(ground['nodes'])
    audit.counts['ground_equations'] = len(ground['equations'])
    audit.counts['normalization_candidates_agree'] = int(normal[0] == normal[1])
    return ground, facts
