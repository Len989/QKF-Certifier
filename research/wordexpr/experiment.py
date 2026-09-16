"""Post-freeze development experiment, not a new blind external sample."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from research.external.frozen_v1.experiment import check_blob, check_engine, signed, words
from research.observations.model import digest, require
from .checker import check
from .cli import save
from .frontend import CONTRACT, Unsupported, read_source, select
from .producer import derive
from .semantics import evaluate, goal_value

ROOT = Path(__file__).resolve().parents[2]


def specification(entry, target=None):
    return {'schema': 'qkf-word-expression-goal-v1', 'contract': CONTRACT, 'entry': entry,
            'target': ['lowest_set_bit'] if target is None else ['equals', target]}


def run(inputs, output):
    inputs, output = Path(inputs), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    corpus = json.loads((ROOT / 'research/external/frozen_v1/CORPUS.json').read_text())
    check_engine(ROOT)
    originals = {}
    for label in ('jdk_long', 'lucene_bits'):
        raw = (inputs / (label + '.java')).read_bytes()
        save(output / (label + '.identity.json'), check_blob(raw, corpus['sources'][label]))
        originals[label] = raw.decode('utf-8')
        (output / (label + '.java')).write_bytes(raw)
    applicability = []
    for case in corpus['population']:
        entry = {'class': 'Long' if case['source'] == 'jdk_long' else 'BitUtil', 'method': case['method']}
        try:
            ir = read_source(originals[case['source']], entry)
            record = {'id': case['id'], 'status': 'source_parsed', 'nodes': len(ir['nodes'])}
        except Unsupported as exc:
            record = {'id': case['id'], 'status': 'source_unsupported', 'reason': str(exc)}
        applicability.append(record)
    save(output / 'applicability.json', applicability)
    require([x['id'] for x in applicability if x['status'] == 'source_parsed'] == ['jdk_long.lowestOneBit'],
            'unexpected development applicability population')
    source = originals['jdk_long']
    spec = specification({'class': 'Long', 'method': 'lowestOneBit'})
    cert, result = derive(source, spec)
    require(result['status'] == 'certified', 'original lowest-bit certificate')
    save(output / 'lowest.goal.json', spec)
    save(output / 'lowest.certificate.json', cert)
    save(output / 'lowest.result.json', result)
    # Replay in a fresh optimized process, with no search import from the CLI.
    replay = subprocess.run([sys.executable, '-O', '-m', 'research.wordexpr.cli', 'check',
        str(output / 'jdk_long.java'), '--spec', str(output / 'lowest.goal.json'),
        '--certificate', str(output / 'lowest.certificate.json')], cwd=ROOT,
        capture_output=True, text=True, timeout=15)
    require(replay.returncode == 0 and json.loads(replay.stdout)['status'] == 'certified', 'independent CLI replay')
    save(output / 'replay.json', json.loads(replay.stdout))
    cases = [
        ('alternate_lowest', 'return x & (~x + 1L);', None, 'certified'),
        ('local_lowest', 'long t = 0L - x; return t & x;', None, 'certified'),
        ('cancel', 'return (x + 2L) - 2L;', ['input'], 'certified'),
        ('negation', 'return ~x + 1L;', ['neg', ['input']], 'certified'),
        ('ones', 'return x | ~x;', ['not', ['const', 0]], 'certified'),
        ('commute', 'return 1L + x;', ['add', ['input'], ['const', 1]], 'certified'),
        ('irrelevant', 'long t = -x; return x;', ['input'], 'certified'),
        ('wrong_not', 'return x & ~x;', None, 'refuted'),
        ('wrong_identity', 'return x;', None, 'refuted'),
        ('wrong_or', 'return x | -x;', None, 'refuted'),
        ('wrong_clear', 'return x & (x - 1L);', None, 'refuted'),
    ]
    controls = []
    for name, body, target, expected in cases:
        text = 'public class Example { public static long f(long x) {' + body + '} }'
        g = specification({'class': 'Example', 'method': 'f'}, target)
        c, r = derive(text, g)
        require(r['status'] == expected and check(text, g, c) == r, 'constructed control ' + name)
        (output / (name + '.java')).write_text(text, encoding='utf-8')
        save(output / (name + '.goal.json'), g)
        save(output / (name + '.certificate.json'), c)
        save(output / (name + '.result.json'), r)
        controls.append({'name': name, 'status': r['status'], 'native_states': r['source']['native_states'],
                         'classes': r['source']['classes'], 'certificate_sha256': digest(c)})
    population = words(corpus['native'])
    declaration = select(source, spec['entry'])[3]
    java = ('public class Probe {\n' + declaration + '\n'
            'public static void main(String[] args) throws Exception {\n'
            'java.io.BufferedReader r=new java.io.BufferedReader(new java.io.InputStreamReader(System.in));\n'
            'for(String s;(s=r.readLine())!=null;) System.out.println(lowestOneBit(Long.parseLong(s)));\n}}\n')
    with tempfile.TemporaryDirectory(prefix='wordexpr-native-') as d:
        p = Path(d) / 'Probe.java'
        p.write_text(java, encoding='utf-8')
        cp = subprocess.run(['javac', '--release', '17', str(p)], capture_output=True, text=True, timeout=30)
        require(cp.returncode == 0, 'native compilation: ' + cp.stderr)
        ip = '\n'.join(str(signed(x)) for x in population) + '\n'
        native = subprocess.run(['java', '-cp', d, 'Probe'], input=ip,
                                capture_output=True, text=True, timeout=30)
        require(native.returncode == 0, 'native execution: ' + native.stderr)
    outputs = [int(x) & ((1 << 64) - 1) for x in native.stdout.splitlines()]
    require(len(outputs) == len(population), 'native output population')
    ir = cert['source']['ir']
    for x, y in zip(population, outputs):
        require(y == evaluate(ir, x, 64) == goal_value(None, x, 64), 'native/IR/positional oracle disagreement')
    (output / 'Probe.java').write_text(java, encoding='utf-8')
    (output / 'native-input.txt').write_text(ip, encoding='utf-8')
    (output / 'native-output.txt').write_text(native.stdout, encoding='utf-8')
    summary = {'development_not_blind': True, 'external_methods': 12, 'source_parsed': 1,
               'source_unsupported': 11, 'new_external_certified': 1, 'new_external_refuted': 0,
               'native_inputs': len(population), 'native_mismatches': 0,
               'constructed_certified': 7, 'constructed_refuted': 4, 'controls': controls,
               'original_certificate_sha256': digest(cert), 'original_result': result,
               'frozen_baseline_unchanged': True, 'new_lean_theorem': False}
    save(output / 'SUMMARY.json', summary)
    save(output / 'MANIFEST.json', {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(output.rglob('*')) if p.is_file()})
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs')
    parser.add_argument('output')
    args = parser.parse_args()
    print(json.dumps(run(Path(args.inputs).resolve(), Path(args.output).resolve()), sort_keys=True))
