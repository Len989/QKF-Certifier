"""Source-bound composition experiment on a pinned, constructed 17-case corpus.

Use --typed-evidence to consume freshly regenerated run-2 packages. Complete
composition certificates are saved in the chosen output directory/CI artifacts;
the repository retains a regression fingerprint, NOT a hash-only proof. Replay
checks every certificate without search. The strict-floor row stays unresolved.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from .composition_kernel import check, explain
from .composition_program import program, variants
from .composition_spec import dependency_spec, specification
from .model import digest, require
from .run_io import new_path, read_json, write_json

ROOT = Path(__file__).resolve().parents[2]
TYPED = ROOT / 'research/observations/evidence/typed_targets'
EVIDENCE = ROOT / 'research/observations/evidence/composition'
BASELINE = EVIDENCE / 'BASELINE.json'


def source_case(role, name, typed_evidence=TYPED):
    goal = 'maximum' if role == 'descending' else 'cyclic_successor'
    root = Path(typed_evidence) / (role + '.' + name + '.' + goal)
    source = (root / 'source.java').read_bytes().decode('utf-8')
    # The experiment corpus is pinned externally, not chosen by a saved package.
    pinned = TYPED / (role + '.' + name + '.' + goal) / 'source.java'
    require(source.encode('utf-8') == pinned.read_bytes(), 'pinned composition source corpus')
    require(read_json(root / 'goal.json') == dependency_spec(role), 'exact external region goal')
    return source, read_json(root / 'package.json', package=True)


def cases(typed_evidence=TYPED):
    base_sources, base_dependencies = {}, {}
    for role in ('descending', 'ascending'):
        base_sources[role], base_dependencies[role] = source_case(role, 'original', typed_evidence)
    for name, p in variants().items():
        yield {'id': 'wrapper.' + name, 'program': p, 'sources': base_sources,
               'dependencies': base_dependencies, 'population': 'wrapper_control',
               'expected': 'certified' if name in {'original', 'inclusive_minimum'} else 'refuted'}
    for role, name in (('ascending','clear_repair'), ('ascending','first_or'),
                       ('ascending','first_four_bits'), ('ascending','irrelevant_register'),
                       ('descending','plus_one'), ('descending','shared_input'), ('descending','strict')):
        source, dependency = source_case(role, name, typed_evidence)
        expected = 'certified' if name == 'irrelevant_register' else 'unresolved' if name == 'strict' else 'refuted'
        yield {'id': 'source.' + role + '.' + name, 'program': program(),
               'sources': {**base_sources, role: source}, 'dependencies': {**base_dependencies, role: dependency},
               'population': 'source_control', 'expected': expected}


def verify_baseline(output, baseline=BASELINE):
    """Regression identity only: callers first check the full actual proofs."""
    reference = read_json(baseline, package=True)
    require(reference.get('schema') == 'qkf-composition-regression-baseline-v1', 'baseline schema')
    actual = {}
    summary = read_json(Path(output) / 'SUMMARY.json', package=True)
    require(set(summary['cases']) == set(reference['cases']), 'baseline case population')
    for case_id in sorted(reference['cases']):
        require('/' not in case_id and '..' not in case_id, 'baseline case identifier')
        directory = Path(output) / case_id
        proof = directory / 'certificate.json'
        certificate = read_json(proof, package=True) if proof.is_file() else None
        result = read_json(directory / 'result.json', package=True)
        actual[case_id] = {
            'status': result['status'],
            'certificate_sha256': digest(certificate) if certificate is not None else None,
            'result_sha256': digest(result),
            'program_sha256': digest(read_json(directory / 'program.json')),
            'specification_sha256': digest(read_json(directory / 'goal.json')),
        }
    require(digest(actual) == digest(reference['cases']), 'composition regression fingerprints')
    return {'matched_cases': len(actual), 'meaning': 'identity, not proof acceptance'}


def manifest(output):
    return {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'MANIFEST.json'}


def run(output, *, replay=False, native=False, max_width=5, typed_evidence=TYPED):
    output = Path(output)
    if not replay:
        new_path(output).mkdir(parents=True, exist_ok=False)
    require(not (replay and native), 'native execution is separate from replay')
    if replay:
        require(read_json(output / 'MANIFEST.json', package=True) == manifest(output),
                'complete composition artifact manifest')
    goal = specification()
    population = tuple(cases(typed_evidence))
    dependency_record = {
        case['id']: {role: {'source_sha256': hashlib.sha256(case['sources'][role].encode('utf-8')).hexdigest(),
                           'package_sha256': digest(package)}
                     for role, package in case['dependencies'].items()}
        for case in population}
    if replay:
        require(read_json(output / 'DEPENDENCIES.json') == dependency_record,
                'recomputed composition dependency provenance')
    results = {}
    proof_count = 0
    for case in population:
        directory = output / case['id']
        p, sources = case['program'], case['sources']
        if replay:
            # The caller-controlled population supplies all inputs again. Local
            # files in the evidence directory cannot silently replace them.
            require(read_json(directory / 'program.json') == p, 'retained wrapper identity')
            require(read_json(directory / 'goal.json') == goal, 'retained target identity')
            for role, text in sources.items():
                require((directory / (role + '.java')).read_bytes() == text.encode('utf-8'), 'retained region bytes')
            if case['expected'] == 'unresolved':
                require(not (directory / 'certificate.json').exists(), 'unresolved case has no proof')
                result = read_json(directory / 'result.json', package=True)
                require(result['status'] == 'unresolved' and result['certificate'] is None, 'unresolved report only')
                certificate = None
            else:
                certificate = read_json(directory / 'certificate.json', package=True)
                result = check(p, sources, goal, certificate)
                require(digest(read_json(directory / 'result.json', package=True)) == digest(result), 'recomputed result')
        else:
            from .composition_producer import synthesize
            proposal = synthesize(p, sources, goal, dependencies=case['dependencies'], max_witness_width=4)
            certificate = proposal['certificate']
            result = check(p, sources, goal, certificate) if certificate is not None else proposal
            directory.mkdir()
            write_json(directory / 'program.json', p)
            write_json(directory / 'goal.json', goal)
            for role, text in sources.items():
                (directory / (role + '.java')).write_bytes(text.encode('utf-8'))
            if certificate is not None:
                write_json(directory / 'certificate.json', certificate)
                write_json(directory / 'explanation.json', explain(p, sources, goal, certificate))
            write_json(directory / 'result.json', result)
        require(result['status'] == case['expected'], 'composed experiment outcome: ' + case['id'])
        details = {'population': case['population'], 'status': result['status'],
                   'program_sha256': digest(p), 'specification_sha256': digest(goal),
                   'proof_sha256': digest(certificate) if certificate is not None else None,
                   'order_cases': result.get('checked_order_cases'), 'reason': result.get('reason')}
        if certificate is not None:
            proof_count += 1
            details['certificate_bytes'] = (directory / 'certificate.json').stat().st_size
        if result['status'] == 'refuted':
            details['counterexample'] = {k: result['counterexample'][k] for k in ('input', 'alternative', 'result')}
        if result['status'] == 'unresolved':
            details['bounded_search'] = result['search']
            details['replay_semantics'] = 'report only; no mathematical verdict'
        results[case['id']] = details
        print(json.dumps({'case': case['id'], **details}), flush=True)
    counts = dict(Counter(r['status'] for r in results.values()))
    require(counts == {'certified': 3, 'refuted': 13, 'unresolved': 1} and proof_count == 16,
            'complete constructed composition population')
    summary = {'schema': 'qkf-composition-experiment-v1', 'cases': results, 'counts': counts,
               'proof_certificates': proof_count,
               'scope': 'constructed wrapper and source controls; no external benchmark or full Graal helper claim'}
    if replay:
        require(digest(summary) == digest(read_json(output / 'SUMMARY.json', package=True)), 'replay summary identity')
    else:
        write_json(output / 'SUMMARY.json', summary)
        from .composition_validation import harness, java_results, validate
        canonical = population[0]
        models = {r: x['proofs']['source'] for r, x in canonical['dependencies'].items()}
        validation = validate(canonical['program'], canonical['sources'], models, native=native, max_width=max_width)
        # Execute each negative witness with its ACTUAL wrapper and region bytes.
        negative_native = []
        if native:
            for case in population:
                if case['expected'] != 'refuted':
                    continue
                result = read_json(output / case['id'] / 'result.json', package=True)
                witness = result['counterexample']
                actual = java_results(case['program'], case['sources'], [witness['input']])[0]
                require(actual == witness['result'], 'native replay of composed refutation: ' + case['id'])
                negative_native.append(case['id'])
        validation['native_negative_witnesses'] = negative_native
        validation['native_negative_calls'] = len(negative_native)
        write_json(output / 'VALIDATION.json', validation)
        (output / 'ComposedHarness.java').write_text(harness(canonical['program'], canonical['sources']), encoding='utf-8')
        write_json(output / 'DEPENDENCIES.json', dependency_record)
        write_json(output / 'MANIFEST.json', manifest(output))
    verify_baseline(output)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--typed-evidence', type=Path, default=TYPED)
    p.add_argument('--replay', action='store_true')
    p.add_argument('--native', action='store_true')
    p.add_argument('--max-width', type=int, default=5, choices=range(1,7))
    args = p.parse_args()
    if args.replay and args.native:
        p.error('native execution is separate from no-search replay')
    print(json.dumps(run(args.output, replay=args.replay, native=args.native, max_width=args.max_width, typed_evidence=args.typed_evidence), sort_keys=True))


if __name__ == '__main__': main()
