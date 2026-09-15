"""Bounded oracles for the exact extracted region, separate from slice rules.

The AST interpreter uses full integers. The JVM harness embeds the original
region bytes; its entry is a legal masked word, not the whole Graal helper.
"""
import itertools
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile

# Re-export the original interpreter API for existing validation/tests. Keeping
# it in a pure module lets negative property replay avoid importing this harness.
from .ascending_execution import environment, expression, integer_value, statement
from .ascending_kernel import ALPHABET, Runner
from .ascending_source import extract_region
from .model import require


def input_word(key):
    width, must, may, seed = key
    return [''.join(str((x >> i) & 1) for x in (must, may, seed)) for i in range(width)]


def keys(max_width):
    for width in range(1, max_width + 1):
        for word in itertools.product(ALPHABET, repeat=width):
            yield (width, *(sum(int(a[j]) << i for i, a in enumerate(word)) for j in range(3)))


def successor(key):
    """Independent bounded oracle: enumerate legal numbers in numeric order."""
    width, must, may, seed = key
    legal = [x for x in range(1 << width) if x & must == must and x & ~may == 0]
    return next((x for x in legal if x > seed), legal[0])


def java_values(region, cases):
    java = shutil.which('java'); require(java is not None, 'Java 17+ source launcher required')
    names = region['names']
    signature = f'static long run(int {names[0]}, long {names[2]}, long {names[3]}, long {region["word"]})'
    helper = signature + '{\n' + region['optional_code'] + '\n' + region['code'] + '\nreturn ' + region['word'] + ';\n}'
    harness = 'public class NativeAscendingHarness {\nstatic class CodeUtil {' + region['mask'] + '}\n' + helper + '''
public static void main(String[] args) throws Exception {
  var reader = new java.io.BufferedReader(new java.io.InputStreamReader(System.in));
  String line;
  while ((line = reader.readLine()) != null) {
    String[] x = line.split(" ");
    System.out.println(run(Integer.parseInt(x[0]), Long.parseLong(x[1]),
      Long.parseLong(x[2]), Long.parseLong(x[3])));
  }
}
}
'''
    require(all(1 <= key[0] <= 62 for key in cases), 'native harness payload width 1..62')
    env = os.environ.copy(); lib = Path(java).resolve().parent.parent / 'lib'
    env['LD_LIBRARY_PATH'] = str(lib) + ':' + str(lib / 'server') + (':' + env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    stdin = ''.join(' '.join(map(str, (key[0] + 1, *key[1:]))) + '\n' for key in cases)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'NativeAscendingHarness.java'; path.write_text(harness)
        result = subprocess.run([java, '-ea', '--source', '17', str(path)], input=stdin,
                                text=True, capture_output=True, env=env, timeout=60)
    require(result.returncode == 0, 'native ascending region failed: ' + result.stderr[-1500:])
    values = [int(line) for line in result.stdout.splitlines()]
    require(len(values) == len(cases), 'one Java result per region input')
    return [v & ((1 << key[0]) - 1) for key, v in zip(cases, values)]


def validate(source, cert, *, max_width=6, native=False):
    runner = Runner(source, cert); region = extract_region(source)
    cases = list(keys(max_width)); random_cases = []
    rng = random.Random(14092026)
    for width in [8, 16, 31, 32, 33, 61, 62]:
        mask = (1 << width) - 1
        # Include long carry chains and an absent optional mask.
        random_cases.extend([(width, 0, mask, mask), (width, 0, mask, 0), (width, mask, mask, mask)])
        for _ in range(20):
            may = rng.getrandbits(width); must = rng.getrandbits(width) & may
            random_cases.append((width, must, may, must | (rng.getrandbits(width) & may)))
    all_cases = cases + random_cases
    values = [integer_value(region, key) for key in all_cases]
    for key, value in zip(all_cases, values):
        bits = runner.run(input_word(key))['outputs']
        require(sum(int(y) << i for i, y in enumerate(bits)) == value, 'factor differs from full-integer source execution')
    if native: require(java_values(region, all_cases) == values, 'JVM region differs from mathematical output projection')
    violations = []
    for key, value in zip(cases, values):
        expected = successor(key)
        if value != expected:
            violations.append({'input': list(key), 'output': value, 'expected_cyclic_successor': expected})
    return {'exhaustive_inputs': len(cases), 'exhaustive_widths': [1, max_width],
            'additional_inputs': len(random_cases), 'additional_widths': [8, 16, 31, 32, 33, 61, 62],
            'source_factor_mismatches': 0, 'native_java': 'passed' if native else 'not_run',
            'native_calls': len(all_cases) if native else 0,
            'bounded_successor_violations': len(violations),
            'first_successor_counterexample': violations[0] if violations else None,
            'scope': 'exact extracted region at a supplied legal entry; emitted payload only; successor is a bounded oracle'}
