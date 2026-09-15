"""Pinned upstream-source transfer through the existing four fixed goals.

This is a development/provenance check, not the frozen multi-program benchmark.
Inputs are local unmodified source downloads. Network retrieval belongs to CI.
A lexical source bundle is not a complete Java build. Native validation compiles
only the exact selected regions plus the existing harness declarations.
No typed-target, composition, or Lean-target implementation is imported.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

from .model import digest, require
from .run_io import new_path, read_json, read_source, write_json, write_run
from .run_package import check_package
from .successor_spec import specification as successor_spec
from .upper_spec import specification as upper_spec

BASE_COMMIT = '49372a463bd4a5a86b7962deaa4f38ddecd8234f'
UPSTREAM = {
    'graal_reference': {
        'repository': 'oracle/graal',
        'commit': '3f5efeb49d934f8a0bcb3c115a6a28caa5622975',
        'path': 'compiler/src/jdk.graal.compiler/src/jdk/graal/compiler/core/common/type/IntegerStamp.java',
        'blob': '47a47eb2ac110bc9cc2be2d010140e7b3a55970a',
    },
    'graal_revision': {
        'repository': 'oracle/graal',
        'commit': 'fe089e8354cfe6c3cdbf6375ac9354e3131f17e7',
        'path': 'compiler/src/jdk.graal.compiler/src/jdk/graal/compiler/core/common/type/IntegerStamp.java',
        'blob': 'af4b492f3b0dd81e1c3253ec90f5be372d4e6421',
    },
    'jdk25': {
        'repository': 'openjdk/jdk',
        'commit': '6c48f4ed707bf0b15f9b6098de30db8aae6fa40f',
        'path': 'src/jdk.internal.vm.ci/share/classes/jdk/vm/ci/code/CodeUtil.java',
        'blob': '59af250a69518bb948d442ce1025aaa61f2c5544',
    },
}
GOALS = (('descending', 'maximum'), ('descending', 'bound'),
         ('ascending', 'cyclic_successor'), ('ascending', 'membership'))
SEPARATOR = '\n\n/* Exact upstream JVMCI primitive; lexical bundle, not a Java compilation unit. */\n\n'
SCOPE = ('two revisions of one Graal implementation plus one OpenJDK dependency; '
         'four fixed mathematical goals; not eight independent programs; '
         'no whole-helper, full JVM, new Lean or frozen-benchmark claim')


def goal(profile, claim):
    require((profile, claim) in GOALS, 'fixed upstream transfer goal')
    return (upper_spec if profile == 'descending' else successor_spec)(claim)


def checked_inputs(directory):
    """Use Git object IDs to establish exact downloaded bytes, not correctness."""
    sources, provenance = {}, {}
    for name, identity in UPSTREAM.items():
        text = read_source(Path(directory) / (name + '.java'))
        raw = text.encode('utf-8')
        blob = hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()
        require(blob == identity['blob'], 'upstream file identity: ' + name)
        sources[name] = text
        provenance[name] = {**identity, 'bytes': len(raw),
                            'sha256': hashlib.sha256(raw).hexdigest()}
    return sources, provenance


def run(inputs, output, *, native=False):
    from .run_producer import verify
    sources, provenance = checked_inputs(inputs)
    output = new_path(output)
    output.mkdir(parents=True)
    # Preserve complete originals including upstream notices, not edited fixtures.
    originals = output / 'upstream'
    originals.mkdir()
    for name, source in sources.items():
        (originals / (name + '.java')).write_bytes(source.encode('utf-8'))
    cases, validations, raw_controls = {}, {}, {}
    for name in ('graal_reference', 'graal_revision'):
        source = sources[name] + SEPARATOR + sources['jdk25']
        for profile, claim in GOALS:
            # A missing dependency must not be silently replaced by a shim.
            if profile not in raw_controls.get(name, {}):
                raw_result, raw_package = verify(sources[name], goal(profile, claim), profile=profile)
                require(raw_result['status'] == 'unsupported' and raw_package is None,
                        'raw upstream without its primitive must not certify')
                raw_controls.setdefault(name, {})[profile] = raw_result
            spec = goal(profile, claim)
            started = time.perf_counter()
            result, package = verify(source, spec, profile=profile)
            elapsed = time.perf_counter() - started
            require(result['status'] in {'certified', 'refuted', 'unsupported', 'budget_exhausted'},
                    'upstream experiment cannot hide an internal failure')
            key = name + '.' + profile + '.' + claim
            directory = output / key
            write_run(directory, result, package)
            (directory / 'source.java').write_bytes(source.encode('utf-8'))
            write_json(directory / 'goal.json', spec)
            record = {'status': result['status'], 'verify_seconds': elapsed,
                      'source_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(),
                      'package_sha256': None, 'package_bytes': 0, 'replay_seconds': None}
            if package is not None:
                started = time.perf_counter()
                require(check_package(source, spec, package) == result, 'independent fixed-goal replay')
                record.update(package_sha256=digest(package),
                              package_bytes=(directory / 'package.json').stat().st_size,
                              replay_seconds=time.perf_counter() - started)
                native_key = name + '.' + profile
                if native_key not in validations:
                    model = package['proofs']['source']
                    if profile == 'descending':
                        from .property_validation import validate
                        validations[native_key] = validate(source, model, upper_spec(), max_width=3, native=native)
                    else:
                        from .ascending_validation import validate
                        validations[native_key] = validate(source, model, max_width=4, native=native)
            cases[key] = record
    summary = {'schema': 'qkf-upstream-transfer-v1', 'baseline_commit': BASE_COMMIT,
               'scope': SCOPE, 'inputs': provenance, 'cases': cases,
               'counts': dict(Counter(c['status'] for c in cases.values())),
               'raw_without_dependency': raw_controls, 'bounded_validation': validations}
    write_json(output / 'SUMMARY.json', summary)
    return summary


def replay(directory):
    """Rebuild sources/goals externally; never accept a saved verdict as proof."""
    directory = Path(directory)
    sources, _ = checked_inputs(directory / 'upstream')
    cases = {}
    for name in ('graal_reference', 'graal_revision'):
        source = sources[name] + SEPARATOR + sources['jdk25']
        for profile, claim in GOALS:
            key = name + '.' + profile + '.' + claim
            path = directory / key
            spec = goal(profile, claim)
            require(read_source(path / 'source.java') == source, 'exact lexical bundle at replay')
            require(read_json(path / 'goal.json') == spec, 'independent goal at replay')
            if (path / 'package.json').exists():
                package = read_json(path / 'package.json', package=True)
                result = check_package(source, spec, package)
                cases[key] = {'status': result['status'], 'package_sha256': digest(package)}
            else:
                # No search is run and no unsupported/budget verdict is certified.
                cases[key] = {'status': 'no_certificate', 'package_sha256': None}
    return {'schema': 'qkf-upstream-replay-v1', 'scope': SCOPE, 'cases': cases,
            'counts': dict(Counter(c['status'] for c in cases.values()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    execute = commands.add_parser('run')
    execute.add_argument('inputs', type=Path)
    execute.add_argument('output', type=Path)
    execute.add_argument('--native', action='store_true')
    check = commands.add_parser('replay')
    check.add_argument('directory', type=Path)
    args = parser.parse_args()
    result = run(args.inputs, args.output, native=args.native) if args.command == 'run' else replay(args.directory)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
