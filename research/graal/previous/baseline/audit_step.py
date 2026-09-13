"""Check frozen evidence, denominators and saved certificates without producers."""
import argparse, hashlib, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FULL = 'proved_source_observation_and_whole_word_ssa'
OPS = ['and', 'or', 'xor', 'add', 'sub']


def require(value, message):
    if not value:
        raise ValueError(message)


def read(name):
    return json.loads((ROOT / name).read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def included(observation, spec):
    """Every represented word satisfies every destination constraint."""
    return observation['count'] == 0 or (
        observation['lower'] >= spec['lower'] and observation['upper'] <= spec['upper']
        and observation['must'] & spec['must'] == spec['must']
        and observation['may'] & ~spec['may'] == 0
        and (spec['can_zero'] or not observation['zero']))


def audit():
    require(not sys.flags.optimize, 'Use ordinary Python: assertions must stay enabled')
    from step_run import block_search, NEW_SEARCH
    block_search()
    from freeze_step import verify
    from joint_kernel import replay
    from theory_certificate import replay as theory_replay
    integrity = verify()
    require(integrity == dict(inherited_files=201, frozen_files=281), 'freeze membership')
    cases = read('CASES.json')
    require(cases['selected'] == 5 and [c['operation'] for c in cases['cases']] == OPS, 'selection')
    counts = {}; accounting = {}; full_replays = 0
    for mode, expected in [('control', ['or']), ('joint', ['and', 'or'])]:
        summary = read(f'results/{mode}/summary.json')
        require(summary['selected'] == 5 and [r['operation'] for r in summary['records']] == OPS, 'denominator: ' + mode)
        proved = []; rows = []
        for row in summary['records']:
            op = row['operation']; base = ROOT / 'results' / mode / op
            source = json.loads((base / 'source.json').read_text())
            require(source == row['source'], 'source record: ' + op)
            require(source['mode'] == mode and source['operation'] == op, 'source identity')
            status = row['status']
            if status == FULL:
                require(source['status'] == 'source_observation_produced', 'source completion')
                cp = base / 'source_certificate.json'
                fixture = ROOT / 'core/fixtures/corpus' / op.capitalize() / 'solution.mlir'
                wp = base / 'word/certificates' / (op.capitalize() + '.json')
                require(sha(cp) == source['source_certificate_sha256'], 'source certificate hash')
                require(cp.stat().st_size == source['source_certificate_bytes'], 'source certificate size')
                require(sha(fixture) == source['ssa_sha256'], 'SSA provenance')
                require(sha(ROOT / 'source/IntegerStamp.java') == source['source_sha256'], 'Java provenance')
                certificate = json.loads(cp.read_text())
                require(certificate['source_observation']['source_sha256'] == source['source_sha256'], 'certificate Java provenance')
                require(certificate['operation'] == op, 'certificate operation')
                word = row['word']; worker = json.loads((base / 'replay.json').read_text())
                require(worker == row['replay'] and worker['status'] == FULL, 'combined replay')
                require(worker['search_modules_loaded'] == [], 'combined replay search')
                require(worker['source_certificate_sha256'] == sha(cp) and worker['word_certificate_sha256'] == sha(wp), 'replay certificate link')
                require(worker['ssa_sha256'] == sha(fixture), 'replay SSA link')
                require(word['producer']['certificate_sha256'] == sha(wp), 'word producer certificate')
                require(word['replay']['search_modules_loaded'] == [], 'old word replay search')
                require(word['status'] == worker['word_verification']['status'] == 'proved_original_whole_all_positive_widths', 'whole-word status')
                require(worker['source_execution_widths'] == [1, 8, 16, 32, 64], 'source width scope')
                require((worker['source_leaves'], worker['hull_calls']) == ((5, 4) if op == 'and' else (1, 0)), 'complete source coverage')
                require(word == json.loads((base / 'word/summary.json').read_text())['records'][0], 'word run record')
                proved.append(op); full_replays += 1
                rows.append(dict(operation=op, status=status, source_leaves=worker['source_leaves'], hull_calls=worker['hull_calls']))
            else:
                require(status == source['status'] == 'adapter_unsupported', 'unreported failure: ' + op)
                require('word' not in row and 'replay' not in row and bool(source['error']), 'unsupported case accounting')
                rows.append(dict(operation=op, status=status, reason=source['error']))
        require(proved == expected, 'coverage: ' + mode)
        counts[mode] = dict(proved=len(proved), selected=5, operations=proved)
        accounting[mode] = rows
    joint = read('validation/joint_v1/results.json')
    native = read('validation/source_bridge_v1/results.json')
    require(joint['status'] == native['status'] == 'passed', 'validation status')
    require(joint['exhaustive_summaries'] == sum(r['summaries'] for r in joint['exhaustive']) == 24174, 'summary denominator')
    require(joint['exhaustive_bit_queries'] == sum(r['bit_queries'] for r in joint['exhaustive']) == 86134, 'bit denominator')
    require(joint['wide_summaries'] == 768 and joint['large_analytic_cases'] == 12 and len(joint['negative_checks']) == 10, 'joint validation scope')
    require(native['source_calls'] == native['carrier_equivalences'] == 25454 and native['hull_specializations'] == 2773, 'native create denominator')
    require(native['projection_checks'] == sum(r['checks'] for r in native['projection']) == 17320, 'source projection denominator')
    require(native['source_errors'] == native['mismatches'] == [] and len(native['negative_checks']) == 9, 'native validation failures')
    require(all(v == 'passed' for v in native['source_variants'].values()) and len(native['source_variants']) == 2, 'source variants')
    saved = sorted((ROOT / 'validation/joint_v1').glob('certificate_*.json'))
    strict = read('results/strict_joint/joint.json')
    require(len(saved) == joint['saved_certificates'] == strict['certificates'] == 28, 'saved joint certificates')
    require(strict['status'] == 'passed' and strict['search_modules_loaded'] == [], 'strict joint status')
    require([p.name for p in saved] == [r['file'] for r in strict['records']], 'strict joint membership')
    for path, r in zip(saved, strict['records']):
        c = json.loads(path.read_text())
        require(sha(path) == r['sha256'] and replay(c['spec'], c['query'], c) == r['result'], 'joint replay: ' + path.name)
    carriers = sorted((ROOT / 'validation/source_bridge_v1').glob('carrier_certificate_*.json'))
    require(len(carriers) == 6, 'saved native carriers')
    for path in carriers:
        c = json.loads(path.read_text())
        left = replay(c['spec'], {'kind':'summary'}, c['input_certificate'])['answer']
        right = replay(c['output_spec'], {'kind':'summary'}, c['output_certificate'])['answer']
        require(included(left, c['output_spec']) and included(right, c['spec']), 'full carrier equivalence')
    theory = theory_replay(read('theory/certificate.json'))
    require(theory == read('theory/results.json'), 'theory result')
    strict_theory = read('results/strict_theory/theory.json')
    require(all(strict_theory[k] == v for k, v in theory.items()) and strict_theory['search_modules_loaded'] == [], 'strict theory record')
    post = read('postrun/results.json')
    require(post['status'] == 'passed' and len(post['theory_mutations_rejected']) == 4, 'post-run status')
    require([r['width'] for r in post['implicit_bit_examples']] == [4, 8, 32, 64], 'post-run widths')
    for w in [4, 8, 32, 64]:
        c = read(f'postrun/implicit_bit_{w}.json')
        r = replay(c['returned_spec'], {'kind':'summary'}, c['joint_certificate'])['answer']
        stronger = replay(c['strengthened_spec'], {'kind':'summary'}, c['strengthened_certificate'])['answer']
        require(c['returned_spec']['must'] == 0 and r['must'] == 1 and r['count'] == 2, 'implicit bit')
        require(included(r, c['strengthened_spec']) and included(stronger, c['returned_spec']), 'implicit bit carrier equality')
        require(len(c['counterexamples']) == 3, 'three context constraints')
        for x in c['counterexamples']:
            r = replay(x['spec'], {'kind':'bit', 'index':0}, x['certificate'])['answer']
            require(r['support'] == 3 and r['witnesses']['0'] == x['separating_word'], 'weakened context witness')
    loaded = sorted(n for n in sys.modules if n.split('.')[0] in NEW_SEARCH)
    require(loaded == [], 'audit imported a producer or solver')
    return dict(status='passed', integrity=integrity, coverage=counts, accounting=accounting,
                combined_source_word_replays=full_replays, joint_certificates=28,
                native_carrier_certificate_pairs=6, postrun_implicit_bit_examples=4,
                exhaustive_summaries=24174, exhaustive_bit_queries=86134,
                native_create_cases=25454, source_projection_cases=17320,
                negative_checks=dict(joint=10, source_bridge=9, finite_theory=4),
                theory=theory, search_modules_loaded=loaded,
                preserved_history=dict(NiceToMeetYou_whole='11/39', NiceToMeetYou_components='104/411',
                                       previous_Graal_whole='1/5', previous_Graal_SMT='29/40 UNSAT; 11 timeouts; no new SMT run'),
                scope='Development evidence. Complete source mask observation on mask-only KnownBits inputs; concrete joint input certificates and finite ground visibility are separate guarantees.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, default=ROOT / 'audit/AUDIT.json'); a = p.parse_args()
    result = audit(); a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('x') as f:
        json.dump(result, f, indent=2); f.write('\n')
    print(json.dumps({k: result[k] for k in ['status', 'integrity', 'coverage', 'search_modules_loaded']}))
