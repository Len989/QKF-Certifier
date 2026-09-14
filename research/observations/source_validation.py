"""Independent integer execution and optional execution of the exact Java helper."""
import itertools
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .java_words import extract_mask, extract_method
from .model import require
from .source_factor import Runner


def integer_guard(guard, optional, trial, right, tests):
    tag = guard[0]
    if tag == 'optional': return optional
    if tag == 'test':
        t = tests[guard[1]]; bound = right + t['offset']; op = t['op']
        return {'<': trial < bound, '<=': trial <= bound, '==': trial == bound,
                '!=': trial != bound, '>': trial > bound, '>=': trial >= bound}[op]
    if tag == 'not': return not integer_guard(guard[1], optional, trial, right, tests)
    a = integer_guard(guard[1], optional, trial, right, tests)
    b = integer_guard(guard[2], optional, trial, right, tests)
    return a and b if tag == 'and' else a or b


def integer_execute(ir, key):
    width, bound, must, may, initial = key
    optional = may & ~must & ((1 << width) - 1)
    value = initial; right = key[int(ir['comparison_word'][-1])]
    for position in reversed(range(width)):
        bit = 1 << position
        if integer_guard(ir['guard'], bool(optional & bit), value | bit, right, ir['tests']): value |= bit
    return value


def records(ir, max_width):
    columns = {c['symbol']: c['input_bits'] for c in ir['columns']}
    for width in range(1, max_width + 1):
        for word in itertools.product(sorted(columns), repeat=width):
            inputs = [sum(columns[a][j] << i for i, a in enumerate(word)) for j in range(4)]
            proposed = sum(int(a[3]) << i for i, a in enumerate(word))
            yield word, (width, *inputs), proposed


def java_values(source, keys):
    java = shutil.which('java'); require(java is not None, 'Java 17+ source launcher required')
    _, _, helper = extract_method(source)
    mask, _ = extract_mask(source)
    harness = 'public class NativeObservationHarness {\nstatic class CodeUtil { ' + mask + ' }\n' + '''
static class Assertions { static String errorMessageContext(Object... args) { return "input contract"; } }
''' + helper + '''
public static void main(String[] args) throws Exception {
  var reader = new java.io.BufferedReader(new java.io.InputStreamReader(System.in));
  String line;
  while ((line = reader.readLine()) != null) {
    String[] x = line.split(" ");
    System.out.println(setOptionalBits(Integer.parseInt(x[0]), Long.parseLong(x[1]),
      Long.parseLong(x[2]), Long.parseLong(x[3]), Long.parseLong(x[4])));
  }
}
}
'''
    env = os.environ.copy()
    lib = Path(java).resolve().parent.parent / 'lib'
    env['LD_LIBRARY_PATH'] = str(lib) + ':' + str(lib / 'server') + (':' + env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    # Payload width w is embedded in a Java helper of width w+1 with zero sign.
    stdin = ''.join(' '.join(map(str, (key[0] + 1, *key[1:]))) + '\n' for key in keys)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'NativeObservationHarness.java'; path.write_text(harness)
        r = subprocess.run([java, '-ea', '--source', '17', str(path)], input=stdin, text=True,
                           capture_output=True, env=env, timeout=60)
    require(r.returncode == 0, 'native Java execution failed: ' + r.stderr[-1500:])
    values = [int(line) for line in r.stdout.splitlines()]
    require(len(values) == len(keys), 'one Java answer per concrete input')
    return dict(zip(keys, values))


def validate(source, cert, *, max_width=5, native=False):
    runner = Runner(source, cert); ir = cert['word']['source_ir']
    cases = list(records(ir, max_width)); keys = sorted({key for _, key, _ in cases})
    expected = {key: integer_execute(ir, key) for key in keys}
    if native:
        actual = java_values(source, keys)
        require(actual == expected, 'Java helper disagrees with integer profile')
    counts = {w: {'width': w, 'words': 0, 'mismatches': 0} for w in range(1, max_width + 1)}
    for word, key, proposed in cases:
        require(runner.run(word)['accepted'] == (proposed == expected[key]), 'source-derived factor disagrees with execution')
        counts[key[0]]['words'] += 1
    return {'words': len(cases), 'concrete_inputs': len(keys), 'mismatches': 0,
            'native_java': 'passed' if native else 'not_run', 'by_width': list(counts.values()),
            'scope': 'legal column words represented by concrete inputs, bounded unsigned payload with an extra zero sign bit'}
