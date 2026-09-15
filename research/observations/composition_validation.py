"""Bounded numerical and native controls, separate from composition proof replay.

Java embeds the checked original helper/region bytes, with a wrapper generated
from the external JSON program. This tests the small wrapper lowering; it is NOT
a formal Java compiler, an all-JVM-width theorem or execution of Graal create.
"""
from collections import Counter
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile

from .ascending_source import extract_region
from .composition_execution import Execution
from .composition_program import INPUTS, inspect
from .composition_producer import bounded_inputs
from .composition_spec import valid_result
from .java_words import extract_mask, extract_method
from .model import require


def oracle(inputs):
    """Independent bounded enumeration in numeric order; no reused pass/monitor."""
    width, m, a, b = (inputs[k] for k in ('width', 'must', 'may', 'bound'))
    y = next((x for x in range(b, 1 << width) if x & m == m and not x & ~a), None)
    return {'kind': 'empty'} if y is None else {'kind': 'value', 'value': y}


def wide_oracle(inputs):
    """Independent digit-DP feasibility + lexicographic reconstruction.

No floor or successor pass. feasible[i][already_greater] asks whether the i
least significant remaining bits can finish a legal word >= the bound.
"""
    width, m, a, b = (inputs[k] for k in ('width', 'must', 'may', 'bound'))
    allowed = [range((m >> i) & 1, ((a >> i) & 1) + 1) for i in range(width)]
    feasible = [[True, True]]
    for i in range(width):
        bound_bit = (b >> i) & 1
        equal_ok = any(bit >= bound_bit and feasible[-1][int(bit > bound_bit)] for bit in allowed[i])
        feasible.append([equal_ok, True])
    if not feasible[width][0]:
        return {'kind': 'empty'}
    value, greater = 0, False
    for i in reversed(range(width)):
        bound_bit = (b >> i) & 1
        bit = next(bit for bit in allowed[i]
                   if (greater or bit >= bound_bit) and feasible[i][int(greater or bit > bound_bit)])
        greater = greater or bit > bound_bit
        value |= bit << i
    return {'kind': 'value', 'value': value}


def additional_inputs():
    rng = random.Random(1509202603)
    result = []
    for width in (8, 16, 31, 32, 33, 61, 62, 64, 127, 256, 512, 4096):
        mask = (1 << width) - 1
        alternating = sum(1 << i for i in range(0, width, 2))
        triples = [(0, 0, 0), (0, 0, 1), (mask, mask, mask), (mask, mask, 0),
                   (0, mask, mask), (0, mask, 0), (0, 1 << (width - 1), 1),
                   (1, alternating, 2), (1, mask, mask - 1),
                   (0, mask >> 1, mask)]
        for _ in range(20):
            may = rng.getrandbits(width)
            must = rng.getrandbits(width) & may
            triples.append((must, may, rng.getrandbits(width)))
        result.extend({'width': width, 'must': m, 'may': a, 'bound': b} for m, a, b in triples)
    return result


def harness(program, sources):
    info = inspect(program)
    _, _, helper = extract_method(sources['descending'])
    mask, _ = extract_mask(sources['descending'])
    region = extract_region(sources['ascending'])
    ns = region['names']
    signature = f'static long ascend(int {ns[0]}, long {ns[2]}, long {ns[3]}, long {region["word"]})'
    ascending = signature + '{\n' + region['optional_code'] + '\n' + region['code']
    ascending += '\nreturn ' + region['word'] + ' & CodeUtil.mask(' + ns[0] + '-1);\n}'
    mapping = {k: '_v' + str(i) for i, k in enumerate(info['names']) if k != 'alternative'}
    operators = {'eq': '==', 'ne': '!=', 'ult': '<', 'ule': '<=', 'ugt': '>', 'uge': '>='}

    def emit(node):
        if node['op'] == 'empty':
            return 'return new Answer(false, 0);'
        if node['op'] == 'value':
            return 'return new Answer(true, ' + mapping[node['word']] + ');'
        if node['op'] == 'if':
            op, left, right = node['test']
            return ('if (' + mapping[left] + ' ' + operators[op] + ' ' + mapping[right] + ') {\n'
                    + emit(node['yes']) + '\n} else {\n' + emit(node['no']) + '\n}')
        role, args = node['role'], node['args']
        keys = ('bound', 'must', 'may', 'seed') if role == 'descending' else ('must', 'may', 'seed')
        fn = 'setOptionalBits' if role == 'descending' else 'ascend'
        return ('long ' + mapping[node['bind']] + ' = ' + fn + '(width+1, '
                + ', '.join(mapping[args[k]] for k in keys) + ');\n' + emit(node['then']))

    wrapper = 'static Answer run(int width, ' + ', '.join('long ' + mapping[k] for k in INPUTS) + ') {\n'
    wrapper += emit(program['entry']) + '\n}'
    origin = sources['descending']
    notice = origin[:origin.index('*/') + 2] + '\n' if origin.startswith('/*') else ''
    notice += '// Generated bounded validation harness; not a whole-Graal verification claim.\n'
    return (notice + 'import java.io.*;\npublic class ComposedHarness {\n'
            'record Answer(boolean present, long value) {}\n'
            'static class CodeUtil {' + mask + '}\n'
            'static class Assertions { static String errorMessageContext(Object... x){return "input";} }\n'
            + helper + '\n' + ascending + '\n' + wrapper + '''
public static void main(String[] args) throws Exception {
    var input = new BufferedReader(new InputStreamReader(System.in));
    String line;
    while ((line = input.readLine()) != null) {
        String[] p = line.split(" ");
        Answer result = run(Integer.parseInt(p[0]), Long.parseLong(p[1]),
                            Long.parseLong(p[2]), Long.parseLong(p[3]));
        System.out.println(result.present() ? "value " + result.value() : "empty");
    }
}
}
''')


def java_results(program, sources, cases):
    java, javac = shutil.which('java'), shutil.which('javac')
    require(java is not None and javac is not None, 'JDK required for bounded composed control')
    require(all(1 <= c['width'] <= 62 for c in cases), 'native composed payload widths 1..62')
    text = ''.join(' '.join(str(c[k]) for k in ('width', *INPUTS)) + '\n' for c in cases)
    env = os.environ.copy()
    lib = Path(java).resolve().parent.parent / 'lib'
    env['LD_LIBRARY_PATH'] = str(lib) + ':' + str(lib / 'server') + ':' + env.get('LD_LIBRARY_PATH', '')
    with tempfile.TemporaryDirectory() as temp:
        source = Path(temp) / 'ComposedHarness.java'
        source.write_text(harness(program, sources), encoding='utf-8')
        compilation = subprocess.run([javac, '--release', '17', str(source)],
                                     text=True, capture_output=True, env=env, timeout=45)
        require(compilation.returncode == 0, 'native wrapper compilation: ' + compilation.stderr[-2000:])
        execution = subprocess.run([java, '-ea', '-cp', temp, 'ComposedHarness'], input=text,
                                   text=True, capture_output=True, env=env, timeout=45)
        require(execution.returncode == 0, 'native wrapper execution: ' + execution.stderr[-2000:])
    lines = execution.stdout.splitlines()
    require(len(lines) == len(cases), 'one native answer per composed input')
    return [{'kind': 'empty'} if line == 'empty' else {'kind': 'value', 'value': int(line.split()[1])}
            for line in lines]


def validate(program, sources, models, *, max_width=5, native=False):
    runner = Execution(sources, models)
    cases = list(bounded_inputs(max_width))
    extra = additional_inputs()
    counts = Counter()
    calls = Counter()
    paths = Counter()
    values = []
    for inputs in cases + extra:
        execution = runner.run(program, inputs, check_factor=True)
        actual = execution['result']
        expected = oracle(inputs) if inputs['width'] <= max_width else wide_oracle(inputs)
        require(actual == expected, 'composed answer differs from independent numerical minimum')
        require(valid_result(actual, inputs['width']), 'tagged mathematical result')
        values.append(actual)
        counts[actual['kind']] += 1
        paths[execution['trace'][-1]['path']] += 1
        for event in execution['trace']:
            if event['op'] == 'call':
                calls[event['role']] += 1
    selected = [(c, v) for c, v in zip(cases + extra, values) if c['width'] <= 62]
    if native:
        require(java_results(program, sources, [c for c, _ in selected]) == [v for _, v in selected],
                'native wrapper differs from mathematical composition')
    return {'exhaustive_inputs': len(cases), 'exhaustive_widths': [1, max_width],
            'additional_inputs': len(extra), 'additional_widths': sorted({c['width'] for c in extra}),
            'outcomes': dict(counts), 'executed_region_calls': dict(calls), 'return_paths': dict(paths),
            'integer_target_mismatches': 0, 'source_factor_mismatches': 0,
            'native_java': 'passed' if native else 'not_run', 'native_calls': len(selected) if native else 0,
            'scope': 'bounded validation of the composed JSON program and generated Java wrapper; no all-JVM-width theorem'}
