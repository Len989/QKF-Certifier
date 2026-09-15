"""Compare translated typed targets with the 18 legacy results; add 5 change goals.

Default creates fresh source/target packages. --replay checks existing packages
against independently reconstructed goals and repository source evidence,
without invoking any producer. The two populations are reported separately.
"""
import argparse
from collections import Counter
import hashlib
from pathlib import Path

from .model import digest, require
from .run_io import new_path, read_json, write_json, write_run
from .run_package import check_package, create_package, explain_package
from .run_unified_experiment import retained_cases
from .target_templates import from_legacy, template


def cases():
    for case in retained_cases():
        yield {**case, 'goal': from_legacy(case['spec']), 'population': 'legacy_translation'}
        if case['profile'] == 'ascending' and case['spec']['claim'] == 'cyclic_successor':
            yield {**case, 'id': 'ascending.' + case['name'] + '.changes',
                   'goal': template('ascending', 'changes'), 'population': 'new_formula',
                   'expected': 'refuted' if case['name'] in {'first_or', 'first_four_bits'} else 'certified'}


def run(output, *, replay=False):
    output = Path(output)
    if not replay:
        new_path(output).mkdir(parents=True, exist_ok=False)
    results = {}
    for case in cases():
        source, goal, profile = case['source'], case['goal'], case['profile']
        reference = None
        if case['population'] == 'legacy_translation':
            old = create_package(source, case['spec'], profile,
                                 case['source_certificate'], case['property_certificate'])
            reference = check_package(source, case['spec'], old)['property']
        directory = output / case['id']
        if replay:
            package = read_json(directory / 'package.json', package=True)
            result = check_package(source, goal, package, profile=profile)
        else:
            from .run_producer import verify
            result, package = verify(source, goal, profile=profile)
            require(package is not None, 'typed source and target search budget')
            require(check_package(source, goal, package) == result, 'fresh typed replay')
            write_run(directory, result, package)
            (directory / 'source.java').write_bytes(source.encode('utf-8'))
            write_json(directory / 'goal.json', goal)
            write_json(directory / 'explanation.json', explain_package(source, goal, package))
        require(result['status'] == case['expected'], 'typed target experiment outcome: ' + case['id'])
        if reference is not None:
            require(reference['status'] == result['status'], 'legacy and formula verdict agreement')
        details = result['property']
        results[case['id']] = {
            'population': case['population'], 'status': details['status'],
            'observations': details['observations'], 'closed_states': details.get('closed_states'),
            'checked_transitions': details.get('checked_transitions'),
            'witness_width': details.get('witness_width'),
            'legacy_closed_states': reference.get('closed_states') if reference else None,
            'package_sha256': digest(package), 'specification_sha256': digest(goal),
        }
    counts = {p: dict(Counter(r['status'] for r in results.values() if r['population'] == p))
              for p in ('legacy_translation', 'new_formula')}
    require(len(results) == 23 and counts['legacy_translation'] == {'certified': 11, 'refuted': 7}
            and counts['new_formula'] == {'certified': 3, 'refuted': 2}, 'complete typed-target population')
    summary = {'schema': 'qkf-typed-target-experiment-v1', 'cases': results, 'counts': counts,
               'scope': 'same 9 sources; 18 translated goals and 5 new formula cases; no new source language or Lean result'}
    if not replay:
        write_json(output / 'SUMMARY.json', summary)
        write_json(output / 'MANIFEST.json', {
            path.relative_to(output).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(output.rglob('*')) if path.is_file()})
    else:
        require(digest(summary) == digest(read_json(output / 'SUMMARY.json')), 'replayed package summary identity')
    return summary


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--replay', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.output, replay=args.replay), sort_keys=True))


if __name__ == '__main__': main()
