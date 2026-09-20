"""PR31 development: retained PR24 sources, explicit goals and negative controls.

Fresh runs execute Java; replay never imports native/search producers. Costs
are separate from deterministic proof data. This is not the Run27 holdout.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import time

from research.observations.model import integer, require
from research.signed_bridge.cli import load as read_json
from research.signed_bridge.experiment import save, sha
from research.signed_observations.experiment import cases as previous_cases
from research.signed_predicates.frontend import read_source, select, target_value
from research.signed_predicates.semantics import evaluate
from research.signed_runtime.runtime import load as load_runtime
from research.unified.v4 import check, explain
from .common import prepare

ROOT = Path(__file__).resolve().parents[2]
POWER = ['and', ['positive'], ['popcount_eq', 1]]
CONSTRUCTED = (
    ('no_zero_guard', 'return (x & (x - 1)) == 0;', POWER, 'refuted'),
    ('no_sign_guard', 'return x != 0 && (x & (x - 1)) == 0;', POWER, 'refuted'),
    ('wrong_connective', 'return x > 0 || (x & (x - 1)) == 0;', POWER, 'refuted'),
    ('small_width_only', 'return x > 0 || (x == 2 && x < 0);', ['positive'], 'refuted'),
    ('sign', 'return x < 0;', ['negative'], 'certified'),
    ('constant', 'return true;', ['or', ['negative'], ['nonnegative']], 'certified'),
    ('nonzero', 'return x > 0 | x < 0;', ['not', ['popcount_eq', 0]], 'certified'),
    ('count_two', 'long y = x & (x - 1); return (y & (y - 1)) == 0;', ['popcount_le', 2], 'certified'),
)


def target(selection, formula):
    return {'schema': 'qkf-target-v2', 'kind': 'signed_boolean_predicate',
            'source': {'entry': selection['entry'], 'word_type': selection['word_type']},
            'goal': formula}


def cases(inputs):
    for name, text, selection, width in previous_cases(Path(inputs)):
        if width is not None:
            yield name, text, target(selection, POWER), width, True, 'certified'
    for name, body, formula, expected in CONSTRUCTED:
        text = 'class Demo { public static boolean f(long x) { ' + body + ' } }'
        selection = {'entry': {'class': 'Demo', 'method': 'f'}, 'word_type': 'long'}
        yield name, text, target(selection, formula), 64, False, expected


def run(inputs, output, *, replay=False):
    output = Path(output)
    if replay:
        manifest = read_json(output/'MANIFEST.json')
        actual = {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
        require(set(manifest) == actual-{'MANIFEST.json'}, 'target experiment file set')
        for path, expected in manifest.items():
            require(sha((output/path).read_bytes()) == expected, 'target experiment artifact: '+path)
    else:
        require(not output.exists(), 'new target experiment directory required')
        output.mkdir(parents=True)
    results, times = {}, {}
    for name, source, goal, width, external, expected in cases(inputs):
        directory = output/name
        if replay:
            require((directory/'source.java').read_text() == source and read_json(directory/'target.json') == goal,
                    'source/independent-goal identity')
            proof = read_json(directory/'proof.json')
        else:
            from research.unified.v4 import prove
            start = time.perf_counter()
            result, proof = prove(source, goal)
            times[name] = {'discovery_and_builtin_check_seconds': time.perf_counter()-start,
                           'includes': 'source model, observation search, checked runtime load, target search, independent replay'}
            require(proof is not None, 'expected proof case exhausted')
            directory.mkdir()
            (directory/'source.java').write_text(source, encoding='utf-8')
            save(directory/'target.json', goal)
            save(directory/'proof.json', proof)
        start = time.perf_counter()
        result = check(source, goal, proof)
        explanation = explain(source, goal, proof)
        if not replay:
            times[name]['check_and_explain_seconds'] = time.perf_counter()-start
        require(result['status'] == expected, 'unexpected target verdict')
        compiled, selection = prepare(goal)
        runner, _ = load_runtime(source, selection, proof['proof']['observations'])
        ir = read_source(source, selection['entry'], selection['word_type'])
        harness = sha((ROOT/'research/signed_predicates/experiment.py').read_bytes())
        if replay:
            native = read_json(directory/'native.json')
        else:
            from research.signed_predicates.experiment import native as run_java, population
            xs = population(width) if external else sorted(set(range(256)) | {1 << 63, (1 << 63)-1, (1 << 64)-1})
            declaration = select(source, selection['entry'], word_type=selection['word_type'])[3]
            start = time.perf_counter()
            ys = run_java(declaration, selection['entry']['method'], selection['word_type'], width, xs)
            times[name]['native_execution_seconds'] = time.perf_counter()-start
            native = {'width': width, 'inputs': xs, 'outputs': ys, 'source_sha256': ir['source_sha256'],
                      'declaration_sha256': ir['declaration_sha256'], 'harness_sha256': harness}
            save(directory/'native.json', native)
        require(native['width'] == width and native['source_sha256'] == ir['source_sha256']
                and native['declaration_sha256'] == ir['declaration_sha256']
                and native['harness_sha256'] == harness, 'native identity')
        xs, ys = native['inputs'], native['outputs']
        require(type(xs) is list and type(ys) is list and len(xs) == len(ys)
                and xs == sorted(set(xs)) and all(integer(x, 0, (1 << width)-1) for x in xs)
                and all(type(y) is bool for y in ys), 'native record shape')
        require(len(xs) == ((69711 if width == 32 else 69839) if external else 259), 'native population size')
        mismatches = 0
        for x, y in zip(xs, ys):
            require(y == evaluate(ir, x, width) == runner.value(x, width), 'Java/IR/row mismatch')
            mismatches += y != target_value(goal['goal'], x.bit_count(), x >> (width-1))
        if expected == 'certified':
            require(mismatches == 0, 'certified target/native mismatch')
        elif name != 'small_width_only':
            require(mismatches > 0, 'negative control needs an actual native target mismatch')
        else:
            require(mismatches == 0, 'small-width-only control should agree at native width')
        for witness in result['inner']['target'].get('native_width_witnesses', []):
            require(witness['input'] in xs and ys[xs.index(witness['input'])] == witness['output'],
                    'native-width witness must be among executed Java inputs')
        record = {'status': result['status'], 'model_states': result['inner']['runtime']['model_states_at_load'],
                  'classes': result['inner']['runtime']['classes'],
                  'product_states': result['inner']['target'].get('product_states'),
                  'witness_width': result['inner']['target'].get('witness_width'),
                  'native_inputs': len(xs), 'native_target_mismatches': mismatches,
                  'source_ir_row_mismatches': 0, 'external_development': external,
                  'proof_sha256': sha((directory/'proof.json').read_bytes())}
        if replay:
            require(read_json(directory/'result.json') == result and read_json(directory/'explanation.json') == explanation,
                    'replayed target result/explanation')
        else:
            save(directory/'result.json', result)
            save(directory/'explanation.json', explanation)
        results[name] = record
    # Failed discovery controls are retained diagnostics, not replayed searches.
    # All eleven certificate cases above really are checked again during replay.
    if not replay:
        from research.unified.v4 import prove
        source = 'class Demo { public static boolean f(long x) { return x > 0 && (x & (x - 1)) == 0; } }'
        goal = target({'entry': {'class': 'Demo', 'method': 'f'}, 'word_type': 'long'}, POWER)
        controls = {}
        for name, text, budget in [('shift', source.replace('x > 0', '(x >> 1) > 0'), None),
                                   ('source_budget', source, {'max_states': 1}),
                                   ('observation_budget', source, {'max_observations': 0}),
                                   ('product_budget', source, {'max_target_states': 1}),
                                   ('witness_budget', source.replace('x > 0 && ', ''), {'max_witness_bits': 0})]:
            start = time.perf_counter(); outcome, proof = prove(text, goal, budgets=budget)
            times[name] = {'failed_discovery_seconds': time.perf_counter()-start}
            require(proof is None and outcome['status'] == ('unsupported' if name == 'shift' else 'budget_exhausted'),
                    'failure control must not issue a certificate')
            controls[name] = {'source': text, 'target': goal, 'budget': budget, 'result': outcome}
        save(output/'CONTROLS.json', controls)
    controls = read_json(output/'CONTROLS.json')
    summary = {'schema': 'qkf-signed-row-target-development-v1', 'cases': results,
               'proof_counts': dict(sorted(Counter(r['status'] for r in results.values()).items())),
               'control_counts': dict(sorted(Counter(r['result']['status'] for r in controls.values()).items())),
               'external_native_inputs': sum(r['native_inputs'] for r in results.values() if r['external_development']),
               'constructed_native_inputs': sum(r['native_inputs'] for r in results.values() if not r['external_development']),
               'source_ir_row_mismatches': 0, 'new_holdout': False,
               'replay_scope': 'recheck all eleven proof cases and stored native outputs; failure controls retained, not rerun'}
    if replay:
        require(read_json(output/'SUMMARY.json') == summary, 'target summary replay')
    else:
        save(output/'SUMMARY.json', summary); save(output/'PERFORMANCE.json', times)
        save(output/'MANIFEST.json', {p.relative_to(output).as_posix(): sha(p.read_bytes())
                                     for p in sorted(output.rglob('*')) if p.is_file()})
    return summary


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('inputs', type=Path); p.add_argument('output', type=Path)
    p.add_argument('--replay', action='store_true'); a = p.parse_args(argv)
    print(json.dumps(run(a.inputs, a.output, replay=a.replay), sort_keys=True))


if __name__ == '__main__':
    main()
