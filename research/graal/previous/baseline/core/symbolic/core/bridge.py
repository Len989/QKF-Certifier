"""Trusted source-to-ground bridge; no proof search or producer imports.

A row is a word spine of AND, logical shifts and reversal. Every off-spine
word and scalar expression is evaluated in the ORIGINAL environment and
captured. Substitution changes only the spine hole. This matters for x & x
and for a shift amount such as clz(x): neither capture is recomputed on U.

The checker still requires v3 proofs of f(U)=0 and a & U=a. The syntactic
native bridge supplies f(0)=0, a&0=0 and the two meet-compatibility cells.
Only after the generic ground DAG is checked may f(a) be replaced by zero.
"""
import copy
import kernel
import ground_checker

SCHEMA = 'qkf-integrated-saturation-certificate-v4'
MAX_CANDIDATES = 6
MAX_SPINE = 16


def ground_source():
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


def row_apply(frames, argument):
    value = copy.deepcopy(argument)
    for frame in reversed(frames):
        op = frame['operation']
        if op == 'reverse': value = [op, value]
        else: value = [op, value, copy.deepcopy(frame['capture'])]
    return value


def describe(expression):
    """Deterministic candidate, not an applicability proof."""
    frames = []; argument = expression
    while isinstance(argument, list) and argument:
        op = argument[0]
        if op == 'reverse' and len(argument) == 2:
            frames.append(dict(operation=op)); argument = argument[1]
        elif op in {'and', 'shl', 'lshr'} and len(argument) == 3:
            frames.append(dict(operation=op, capture=copy.deepcopy(argument[2]),
                               capture_sort='word' if op == 'and' else 'scalar',
                               capture_environment='original_source'))
            argument = argument[1]
        else: break
        if len(frames) > MAX_SPINE: return None
    if not frames or all(f['operation'] == 'reverse' for f in frames): return None
    # Pull back all output positions through the spine. Its complement is
    # the candidate lost-input mask. This selection is untrusted in effect:
    # its annihilation is proved separately using the old word compiler.
    survival = ['ones']
    for frame in frames:
        op = frame['operation']
        if op == 'reverse': survival = ['reverse', survival]
        else:
            inverse = {'and':'and', 'shl':'lshr', 'lshr':'shl'}[op]
            survival = [inverse, survival, copy.deepcopy(frame['capture'])]
    mask = ['not', survival]
    assert row_apply(frames, argument) == expression
    return dict(expression=copy.deepcopy(expression), argument=copy.deepcopy(argument),
                frames=frames, mask=mask,
                native_rules=[dict(rule='captured_row_preserves_meet_join_and_zero', frame=i)
                              for i in range(len(frames))]
                             + [dict(rule='native_meet_zero_on_named_argument')])


def candidates(source):
    # Validate declarations even if the transformed residual becomes trivial.
    kernel.Compiler(source)
    found = {}; omitted = 0
    def word(expr, path):
        nonlocal omitted
        descriptor = describe(expr)
        if descriptor is not None:
            key = kernel.digest(descriptor)
            if key not in found:
                if len(found) >= MAX_CANDIDATES:
                    omitted += 1; return
                found[key] = dict(candidate_hash=key, descriptor=descriptor, paths=[])
            found[key]['paths'].append(path)
            return  # No overlapping replacements, including inside captures.
        if not isinstance(expr, list) or not expr: return
        op = expr[0]
        if op in {'not', 'reverse'} and len(expr) == 2: word(expr[1], path+[1])
        elif op in {'and', 'or', 'xor'} and len(expr) == 3:
            word(expr[1], path+[1]); word(expr[2], path+[2])
        elif op in {'lowmask', 'highmask'} and len(expr) == 2: scalar(expr[1], path+[1])
        elif op in {'shl', 'lshr'} and len(expr) == 3:
            word(expr[1], path+[1]); scalar(expr[2], path+[2])
        elif op == 'ite' and len(expr) == 4:
            boolean(expr[1], path+[1]); word(expr[2], path+[2]); word(expr[3], path+[3])
    def scalar(expr, path):
        if not isinstance(expr, list) or not expr: return
        if expr[0] in {'clz','clo','ctz','cto'} and len(expr) == 2:
            if isinstance(expr[1], list): word(expr[1], path+[1])
        elif expr[0] in {'add','sub','min','max'} and len(expr) == 3:
            scalar(expr[1], path+[1]); scalar(expr[2], path+[2])
        elif expr[0] == 'ite' and len(expr) == 4:
            boolean(expr[1], path+[1]); scalar(expr[2], path+[2]); scalar(expr[3], path+[3])
    def boolean(expr, path):
        if not isinstance(expr, list) or not expr: return
        if expr[0] in {'and','or','not'}:
            for i, child in enumerate(expr[1:], 1): boolean(child, path+[i])
        elif expr[0] in {'le','lt','eq'} and len(expr) == 3:
            scalar(expr[1], path+[1]); scalar(expr[2], path+[2])
    for i, claim in enumerate(source.get('claims', [])):
        if claim[0] == 'word_eq' and len(claim) == 3:
            word(claim[1], [i,1]); word(claim[2], [i,2])
        elif claim[0] == 'bit_is' and len(claim) == 4:
            word(claim[1], [i,1]); scalar(claim[2], [i,2])
        elif claim[0] == 'scalar' and len(claim) == 2: boolean(claim[1], [i,1])
    return list(found.values()), omitted


def bridge_source(source, candidate):
    d = candidate['descriptor']; a = d['argument']; mask = d['mask']
    return dict(schema=kernel.DSL, name='saturation_native_bridge',
                inputs=copy.deepcopy(source['inputs']),
                parameters=copy.deepcopy(source.get('parameters', [])),
                assume=copy.deepcopy(source.get('assume', True)),
                claims=[['word_eq', row_apply(d['frames'], mask), ['zero']],
                        ['word_eq', ['and', a, mask], a]],
                origin=dict(source_hash=kernel.digest(source), candidate_hash=candidate['candidate_hash']))


def residual(source, accepted):
    replacements = {tuple(path) for candidate in accepted for path in candidate['paths']}
    steps = []
    def walk(value, path):
        if tuple(path) in replacements:
            steps.append(dict(path=path, rule='checked_kernel_saturation'))
            return ['zero'], True
        if not isinstance(value, list): return copy.deepcopy(value), False
        changed = False; result = []
        for i, child in enumerate(value):
            item, change = walk(child, path+[i]); result.append(item); changed |= change
        if not changed or not result: return result, changed
        # Only constant propagation on ancestors of a proved replacement.
        out = result; op = result[0]
        if not isinstance(op, str): return result, changed
        if op in {'clz','clo','ctz','cto'} and len(result) == 2:
            if result[1] in (['zero'], ['ones']):
                ones = result[1] == ['ones']; wanted = op.endswith('o')
                out = 'w' if ones == wanted else 0
        elif op == 'not' and len(result) == 2:
            if result[1] == ['zero']: out = ['ones']
            elif result[1] == ['ones']: out = ['zero']
        elif op == 'reverse' and len(result) == 2 and result[1] in (['zero'], ['ones']): out = result[1]
        elif op in {'shl','lshr'} and len(result) == 3 and result[1] == ['zero']: out = ['zero']
        elif op in {'and','or','xor'} and len(result) == 3:
            a, b = result[1:]
            if op == 'and':
                if ['zero'] in (a,b): out = ['zero']
                elif a == ['ones']: out = b
                elif b == ['ones']: out = a
            elif op == 'or':
                if ['ones'] in (a,b): out = ['ones']
                elif a == ['zero']: out = b
                elif b == ['zero']: out = a
            else:
                if a == ['zero']: out = b
                elif b == ['zero']: out = a
        if out != result: steps.append(dict(path=path, rule='constant_word_or_count', before=result, after=out))
        return out, changed
    result = copy.deepcopy(source)
    result['claims'], _ = walk(source['claims'], [])
    return result, steps


def verify(source, certificate):
    if certificate.get('schema') != SCHEMA or certificate.get('source_hash') != kernel.digest(source):
        raise ValueError('integrated source binding')
    available, _ = candidates(source)
    by_hash = {c['candidate_hash']:c for c in available}
    lemmas = certificate.get('lemmas')
    if not isinstance(lemmas, list) or len(lemmas) > MAX_CANDIDATES: raise ValueError('lemma list')
    accepted = []; seen = set(); bridge_nodes = native_rules = 0; bridge_results = []
    ground = certificate.get('ground_certificate')
    if lemmas:
        ground_result = ground_checker.verify(ground_source(), ground)
    else:
        if ground is not None: raise ValueError('unused ground certificate')
        ground_result = dict(proof_nodes=0)
    for entry in lemmas:
        key = entry.get('candidate_hash')
        if key in seen or key not in by_hash: raise ValueError('candidate binding or duplicate')
        seen.add(key); candidate = by_hash[key]
        if entry.get('candidate') != candidate: raise ValueError('native bridge descriptor or path')
        proof = kernel.verify(bridge_source(source, candidate), entry['bridge_certificate'])
        bridge_nodes += proof['proof_nodes']; bridge_results.append(proof)
        native_rules += len(candidate['descriptor']['native_rules'])
        accepted.append(candidate)
    transformed, steps = residual(source, accepted)
    if certificate.get('residual_hash') != kernel.digest(transformed): raise ValueError('residual binding')
    if certificate.get('rewrite_trace') != steps: raise ValueError('rewrite trace')
    final = kernel.verify(transformed, certificate['residual_certificate'])
    return dict(status='proved_under_original_source_assumptions', claims=len(source['claims']),
                lemmas=len(lemmas), bridge_proof_nodes=bridge_nodes,
                ground_dag_nodes=ground_result['proof_nodes'], ground_instantiations=len(lemmas), native_bridge_rules=native_rules,
                rewrite_steps=len(steps), residual_proof_nodes=final['proof_nodes'],
                total_recorded_steps=bridge_nodes+ground_result['proof_nodes']+len(lemmas)+native_rules+len(steps)+final['proof_nodes'],
                bridge_results=bridge_results, residual_result=final)
