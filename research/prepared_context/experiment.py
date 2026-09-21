"""Serial preregistered PR48 run; each attempt is recorded before execution."""
import argparse
from pathlib import Path
import platform
import subprocess
import sys
import traceback
from .common import (ROOT, HERE, save_json, load_json, digest, require, checkpoint_json,
                     inventory, registered, validate_case, schedule, compare_identity)
from research.causal_comparison.experiment import child


def run(root, shard='all'):
    from .fixtures import cases
    from .analysis import analyze
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    protocol, reg = registered(shard)
    population = [c for c in cases() if shard == 'all' or c['shard'] == shard]
    require(len(population) == len(reg['cases']), 'full shard population')
    for c, entry in zip(population, reg['cases']):
        validate_case(c, entry)
    save_json(root / 'PROTOCOL.json', protocol)
    save_json(root / 'REGISTRATION.json', reg)
    save_json(root / 'RUN.json', dict(shard=shard))
    save_json(root / 'ENGINE.json', dict(
        commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        tree=subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=ROOT, text=True).strip(),
        status=subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True),
        python=sys.version, platform=platform.platform(),
        code_sha256={str(p.relative_to(ROOT)): digest(p.read_text()) for p in sorted(HERE.glob('*.py'))}))
    options = protocol['measurement']
    attempts, failures = [], []
    checkpoint_json(root / 'ATTEMPTS.json', attempts)
    checkpoint_json(root / 'FAILURES.json', failures)

    def attempt(case, route, trial, operation, function):
        row = dict(case=case['name'], route=route, trial=trial, operation=operation, status='started')
        attempts.append(row)
        checkpoint_json(root / 'ATTEMPTS.json', attempts)
        try:
            value = function()
            row['status'] = 'passed'
            return value
        except Exception as error:
            row.update(status='failed', error=type(error).__name__ + ': ' + str(error), traceback=traceback.format_exc())
            failures.append(dict(row))
            return None
        finally:
            checkpoint_json(root / 'ATTEMPTS.json', attempts)
            checkpoint_json(root / 'FAILURES.json', failures)

    for index, case in enumerate(population):
        print(f"PR48 {index + 1}/{len(population)} {case['name']}", file=sys.stderr, flush=True)
        folder = root / case['name']
        folder.mkdir()
        save_json(folder / 'case.json', case)
        audits = {}
        def checked(route, output, history=False):
            command = ['research.prepared_context.verify', str(folder / 'case.json'), route,
                       str(folder / route / 'audit.json'), str(output),
                       '--repetitions', str(options['warm_apply_repetitions'])]
            if history:
                command.append('--history')
            return child(command, output, options['check_timeout_seconds'])
        for route in case['routes']:
            directory = folder / route
            directory.mkdir()
            output = directory / 'audit.json'
            def audit():
                value = child(['research.prepared_context.worker', str(folder / 'case.json'), route, str(output), '--audit'],
                              output, options['build_timeout_seconds'])
                require(value['result']['status'] == case['expected'][route], 'registered outcome')
                return value
            audits[route] = attempt(case, route, 'audit', 'build', audit)
            attempt(case, route, 'audit', 'check', lambda: checked(route, directory / 'audit-check.json', True))
            output = directory / 'memory.json'
            def memory():
                value = child(['research.prepared_context.worker', str(folder / 'case.json'), route, str(output), '--memory'],
                              output, options['build_timeout_seconds'])
                require(audits[route] is not None, 'missing successful audit reference')
                compare_identity(audits[route], value)
                return value
            attempt(case, route, 'memory', 'build', memory)
        # Case index is global even in a CI shard, preserving route schedule.
        global_index = next(i for i, c in enumerate(registered()[1]['cases']) if c['name'] == case['name'])
        for trial in range(options['timing_repeats']):
            for route in schedule(case['routes'], global_index, trial):
                directory = folder / route
                output = directory / f'timing-{trial}.json'
                def timing():
                    value = child(['research.prepared_context.worker', str(folder / 'case.json'), route, str(output)],
                                  output, options['build_timeout_seconds'])
                    require(audits[route] is not None, 'missing successful audit reference')
                    compare_identity(audits[route], value)
                    return value
                attempt(case, route, trial, 'build', timing)
                attempt(case, route, trial, 'check', lambda: checked(route, directory / f'timing-{trial}-check.json'))
        print(f"PR48 completed {case['name']}; attempts={len(attempts)} failures={len(failures)}", file=sys.stderr, flush=True)
    try:
        report = analyze(root)
    except Exception as error:
        failures.append(dict(operation='analysis', error=str(error), traceback=traceback.format_exc()))
        checkpoint_json(root / 'FAILURES.json', failures)
        report = dict(status='failed', failures=len(failures))
    save_json(root / 'SUMMARY.json', report)
    save_json(root / 'MANIFEST.json', inventory(root))
    require(not failures, 'failed attempts retained at ' + str(root))
    return dict(status='passed', cases=report['cases'], pairs=report['pairs'], attempts=report['attempts'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--shard', default='all')
    args = parser.parse_args()
    existed = args.output.exists()
    try:
        import json
        print(json.dumps(run(args.output, args.shard), sort_keys=True))
    except BaseException as error:
        if not existed and args.output.exists():
            checkpoint_json(args.output / 'INTERRUPTION.json', dict(error=str(error), traceback=traceback.format_exc()))
            checkpoint_json(args.output / 'MANIFEST.json', inventory(args.output))
        raise
