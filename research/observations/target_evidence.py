"""Replay the 23 frozen formula proofs from a plain, deduplicated JSON snapshot.

Source bytes and source certificates are existing repository evidence. Only
repeated data are shared; source/property schemas and package digests are intact.
Every reconstructed package is fully checked. This module imports no producer,
target template, old property kernel, native harness, or proof assistant.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .model import digest, require
from .run_io import read_json, write_json, write_run
from .run_package import check_package, create_package, explain_package

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / 'research/observations/evidence/typed_targets/SNAPSHOT.json'
SOURCES = {
    'ascending': ('original', 'clear_repair', 'first_or', 'first_four_bits', 'irrelevant_register'),
    'descending': ('original', 'plus_one', 'strict', 'shared_input'),
}
CLAIMS = {'ascending': ('cyclic_successor', 'membership', 'changes'),
          'descending': ('maximum', 'bound')}
CASE_IDS = tuple(sorted(f'{profile}.{name}.{claim}'
                       for profile, names in SOURCES.items() for name in names
                       for claim in CLAIMS[profile]))


def load_snapshot(path=SNAPSHOT):
    data = read_json(Path(path), package=True)
    require(type(data) is dict and set(data) == {'schema', 'sources', 'goals', 'programs', 'cases'},
            'typed evidence snapshot fields')
    require(data['schema'] == 'qkf-typed-target-snapshot-v1', 'typed evidence snapshot version')
    require(type(data['cases']) is dict and set(data['cases']) == set(CASE_IDS),
            'complete frozen 23-case population')
    return data


def load_case(ident, *, snapshot=None, root=ROOT):
    """Rebuild and check a frozen example, not an arbitrary caller's new goal."""
    require(type(ident) is str and ident in CASE_IDS, 'fixed evidence case')
    data = load_snapshot() if snapshot is None else snapshot
    entry = data['cases'][ident]
    require(type(entry) is dict and set(entry) == {
        'source', 'goal', 'program', 'certificate', 'package_sha256', 'status'}, 'case fields')
    profile, name, claim = ident.split('.')
    require(entry['source'] == profile + '.' + name and entry['goal'] == profile + '.' + claim,
            'case source and goal identity')
    source_info = data['sources'][entry['source']]
    directory = 'ascending' if profile == 'ascending' else 'property'
    suffix = 'certificate.json' if profile == 'ascending' else 'source_certificate.json'
    source_path = f'research/observations/evidence/{directory}/{name}.java'
    proof_path = f'research/observations/evidence/{directory}/{name}.{suffix}'
    require(type(source_info) is dict and set(source_info) == {
        'source', 'source_certificate', 'source_sha256', 'source_certificate_sha256'}, 'source record')
    require(source_info['source'] == source_path and source_info['source_certificate'] == proof_path,
            'only fixed repository evidence paths')
    raw = (Path(root) / source_path).read_bytes()
    source = raw.decode('utf-8')
    source_certificate = read_json(Path(root) / proof_path, package=True)
    require(hashlib.sha256(raw).hexdigest() == source_info['source_sha256']
            and digest(source_certificate) == source_info['source_certificate_sha256'],
            'retained source and certificate identity')
    goal = deepcopy(data['goals'][entry['goal']])
    proof = deepcopy(entry['certificate'])
    require('program' not in proof, 'one shared program definition')
    program = deepcopy(data['programs'][entry['program']])
    require(digest(program) == entry['program'], 'shared program digest')
    proof['program'] = program
    # create_package invokes both real checkers; a hash is not a proof.
    package = create_package(source, goal, profile, source_certificate, proof)
    require(digest(package) == entry['package_sha256'], 'frozen package digest')
    require(package['result']['status'] == entry['status'], 'frozen package verdict')
    return source, goal, package


def compare_fresh(directory):
    """Compare genuinely new source/goal packages with all frozen proof digests."""
    data = load_snapshot()
    for ident in CASE_IDS:
        source, goal, retained = load_case(ident, snapshot=data)
        folder = Path(directory) / ident
        require((folder / 'source.java').read_bytes() == source.encode('utf-8'), 'fresh source identity')
        require(read_json(folder / 'goal.json') == goal, 'fresh goal identity')
        fresh = read_json(folder / 'package.json', package=True)
        require(check_package(source, goal, fresh) == retained['result'], 'fresh replay result')
        require(digest(fresh) == digest(retained), 'fresh and frozen package identity')
    return {'status': 'fresh_packages_match', 'packages': len(CASE_IDS)}


def materialize(directory):
    """Write complete, independently replayed packages to a NEW output directory."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    data = load_snapshot()
    statuses = {}
    for ident in CASE_IDS:
        source, goal, package = load_case(ident, snapshot=data)
        output = directory / ident
        result = check_package(source, goal, package)
        write_run(output, result, package)
        (output / 'source.java').write_bytes(source.encode('utf-8'))
        write_json(output / 'goal.json', goal)
        write_json(output / 'explanation.json', explain_package(source, goal, package))
        statuses[ident] = result['status']
    write_json(directory / 'MANIFEST.json', {
        p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.rglob('*')) if p.is_file()})
    return {'status': 'frozen_evidence_replayed', 'packages': len(statuses), 'cases': statuses}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--compare-fresh', action='store_true')
    args = parser.parse_args()
    result = compare_fresh(args.output) if args.compare_fresh else materialize(args.output)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
