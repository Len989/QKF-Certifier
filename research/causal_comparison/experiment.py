"""Serial frozen experiment. Every scheduled attempt is retained, never retried."""
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback
from .common import (ROOT, HERE, canonical, digest, load_json, save_json, require,
                     registered, validate_case, schedule, compare_identity, matched_verdicts, inventory, checkpoint_json)


def child(command, output, timeout):
    started = time.perf_counter_ns()
    try:
        process = subprocess.run([sys.executable, '-B', '-m'] + command, cwd=ROOT,
                                 capture_output=True, text=True, timeout=timeout)
        record = dict(returncode=process.returncode, timeout=False, stdout=process.stdout, stderr=process.stderr)
    except subprocess.TimeoutExpired as exc:
        def decode(value):
            return value.decode(errors='replace') if type(value) is bytes else (value or '')
        record = dict(returncode=None, timeout=True, stdout=decode(exc.stdout), stderr=decode(exc.stderr))
    record['process_elapsed_ns'] = time.perf_counter_ns() - started
    save_json(output.with_suffix('.process.json'), record)
    require(record['returncode'] == 0, 'child failed: ' + str(output))
    return load_json(output)


def run(root):
    from .fixtures import cases
    from .analysis import analyze
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    protocol, reg = registered()
    population = list(cases())
    require(len(population) == len(reg['cases']), 'complete registered denominator')
    for case, entry in zip(population, reg['cases']):
        validate_case(case, entry)
    save_json(root / 'PROTOCOL.json', protocol)
    save_json(root / 'REGISTRATION.json', reg)
    save_json(root / 'ENGINE.json', dict(
        commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        status=subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True),
        python=sys.version, platform=platform.platform(),
        code_sha256={str(p.relative_to(ROOT)): digest(p.read_text()) for p in sorted(HERE.glob('*.py'))}))
    measurement = protocol['measurement']
    attempts, failures, outcomes = [], [], []

    def attempt(case, route, trial, operation, function):
        row = dict(case=case['name'], route=route, trial=trial, operation=operation)
        try:
            value = function()
            row['status'] = 'passed'
            return value
        except Exception as error:
            row.update(status='failed', error=type(error).__name__ + ': ' + str(error),
                       traceback=traceback.format_exc())
            failures.append(dict(row))
            return None
        finally:
            attempts.append(row)
            # Incremental checkpoint survives an interrupted parent process.
            checkpoint_json(root / 'ATTEMPTS.json', attempts)
            checkpoint_json(root / 'FAILURES.json', failures)

    for index, case in enumerate(population):
        print(f"PR46 {index + 1}/{len(population)} {case['name']}", file=sys.stderr, flush=True)
        folder = root / case['name']
        folder.mkdir()
        save_json(folder / 'case.json', case)
        audits = {}
        for route in case['routes']:
            directory = folder / route
            directory.mkdir()
            if route in case['unavailable']:
                save_json(directory / 'UNAVAILABLE.json', dict(reason=case['unavailable'][route], status='contract_not_supported'))
                continue
            output = directory / 'audit.json'
            def audit():
                value = child(['research.causal_comparison.worker', str(folder / 'case.json'), route,
                               str(output), '--audit'], output, measurement['build_timeout_seconds'])
                require(value['result']['status'] == case['expected'][route], 'registered expected outcome: ' + case['name'] + '/' + route)
                return value
            audits[route] = attempt(case, route, 'audit', 'build', audit)
            if audits[route] is not None:
                outcomes.append(dict(case=case['name'], route=route, status=audits[route]['result']['status']))
            # Even unexpected outcomes may contain certificates: preserve the
            # output and the failed checker attempt instead of deleting them.
            if output.exists():
                checked = directory / 'audit-check.json'
                attempt(case, route, 'audit', 'check', lambda: child(
                    ['research.causal_comparison.verify', str(folder / 'case.json'), route, str(output),
                     str(checked), '--history', '--repetitions', str(measurement['warm_apply_repetitions'])],
                    checked, measurement['check_timeout_seconds']))
            memory_output = directory / 'memory.json'
            def memory():
                value = child(['research.causal_comparison.worker', str(folder / 'case.json'), route,
                               str(memory_output), '--memory'], memory_output, measurement['build_timeout_seconds'])
                require(audits.get(route) is not None, 'no audit reference for memory probe')
                compare_identity(audits[route], value)
                return value
            attempt(case, route, 'memory', 'build', memory)
        for trial in range(measurement['timing_repeats']):
            for route in schedule(case['routes'], index, trial):
                if route in case['unavailable']:
                    continue
                directory = folder / route
                output = directory / f'timing-{trial}.json'
                def timing():
                    value = child(['research.causal_comparison.worker', str(folder / 'case.json'), route,
                                   str(output)], output, measurement['build_timeout_seconds'])
                    require(audits.get(route) is not None, 'no successful audit reference; trial retained')
                    compare_identity(audits[route], value)
                    return value
                attempt(case, route, trial, 'build', timing)
                checked = directory / f'timing-{trial}-check.json'
                if (directory / 'audit.json').exists():
                    attempt(case, route, trial, 'check', lambda: child(
                        ['research.causal_comparison.verify', str(folder / 'case.json'), route,
                         str(directory / 'audit.json'), str(checked), '--repetitions', str(measurement['warm_apply_repetitions'])],
                        checked, measurement['check_timeout_seconds']))
        try:
            matched_verdicts([r['status'] for r in outcomes if r['case'] == case['name']])
        except ValueError as error:
            failures.append(dict(case=case['name'], error=str(error)))
            checkpoint_json(root / 'FAILURES.json', failures)
    save_json(root / 'OUTCOMES.json', outcomes)
    try:
        report = analyze(root)
    except Exception as error:
        failures.append(dict(operation='analysis', error=str(error), traceback=traceback.format_exc()))
        report = dict(status='failed', failures=len(failures))
        checkpoint_json(root / 'FAILURES.json', failures)
    save_json(root / 'SUMMARY.json', report)
    save_json(root / 'MANIFEST.json', inventory(root))
    require(not failures, 'failed attempts retained in ' + str(root))
    return report


if __name__ == '__main__':
    output = Path(sys.argv[1]).resolve()
    existed = output.exists()
    try:
        print(json.dumps(run(output), sort_keys=True))
    except BaseException as error:
        if not existed and output.exists():
            checkpoint_json(output / 'INTERRUPTION.json', dict(error=type(error).__name__ + ': ' + str(error),
                                                               traceback=traceback.format_exc()))
            checkpoint_json(output / 'MANIFEST.json', inventory(output))
        raise
