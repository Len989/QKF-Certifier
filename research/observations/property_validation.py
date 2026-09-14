"""Bounded oracle validation on every disjoint raw input, with optional Java."""
import itertools

from .model import require
from .property_kernel import System
from .source_validation import java_values
from .upper_spec import columns
from .word_execution import integer_execute


def validate(source, source_certificate, maximum_spec, *, max_width=3, native=False):
    system = System(source, source_certificate, maximum_spec)
    raw_bits = sorted({c[:4] for c in columns()})
    keys = []
    for width in range(1, max_width + 1):
        for word in itertools.product(raw_bits, repeat=width):
            keys.append((width, *(sum(int(c[j]) << i for i, c in enumerate(word)) for j in range(4))))
    actual = {key: integer_execute(system.ir, key) for key in keys}
    if native:
        require(java_values(source, keys) == actual, 'native helper differs from integer execution')
    counts = {'inputs': len(keys), 'precondition_inputs': 0, 'outside_precondition': 0,
              'above_bound': 0, 'not_maximal': 0, 'target_alternatives': 0, 'observation_mismatches': 0,
              'native_java': 'passed' if native else 'not_run', 'payload_widths': list(range(1, max_width + 1))}
    for key in keys:
        width, bound, must, may, seed = key; y = actual[key]; optional = may & ~must
        legal = [z for z in range(1 << width) if z & seed == seed and z & ~(seed | optional) == 0]
        require(y in legal, 'output violates the source write footprint')
        feasible = [z for z in legal if z <= bound]
        if feasible:
            counts['precondition_inputs'] += 1
            counts['above_bound'] += y > bound
            counts['not_maximal'] += y <= bound and y != max(feasible)
        else: counts['outside_precondition'] += 1
        for z in legal:
            word = [''.join(str((v >> i) & 1) for v in (bound, must, may, seed, y, z)) for i in range(width)]
            state = system.initial
            for c in word: state = system.advance(state, c)
            require(system.accepting[state[0]], 'derived source factor rejects direct source execution')
            expected = None if seed > bound else ('above_bound' if y > bound else
                                                 'not_maximal' if z <= bound and z > y else None)
            require(system.bad(state) == expected, 'joint observation disagrees with integer target')
            counts['target_alternatives'] += 1
    return counts
