"""Prospectively sealed, sequential frozen-v3 evaluation supervisor.

No QKF imports occur here. Each operation runs in a fresh, isolated child.
This supervisor is not an adversarial sandbox; the acquired Java code is only
executed after the unchanged pure source profile and exact declaration agree.
"""
import collections
import datetime
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import statistics
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
MEMORY = 2 * 1024**3


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, sort_keys=True, indent=2, allow_nan=False)
        f.write('\n')


def population(case_id, width, witnesses=()):
    mask = (1 << width) - 1
    values = {x & mask for x in range(65536)} | {mask, 1 << (width - 1), (1 << (width - 1)) - 1}
    for i in range(width):
        values.update(((1 << i) + d) & mask for d in (-1, 0, 1))
    for i in range(4096):
        data = ('qkf-frozen-v3-native:' + case_id + ':' + str(i)).encode()
        values.add(int.from_bytes(hashlib.sha256(data).digest()[:width // 8], 'big'))
    values.update(int(x) & mask for x in witnesses)
    return sorted(values)


def supervise(command, directory, seconds=120, stdin_path=None):
    directory.mkdir(parents=True, exist_ok=False)
    def limits():
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY, MEMORY))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    env = {k: v for k, v in os.environ.items() if k not in {
        'PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS'}}
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONHASHSEED='0', LC_ALL='C.UTF-8')
    start = time.monotonic()
    timed_out = False
    with (directory / 'stdout.log').open('wb') as out, (directory / 'stderr.log').open('wb') as err:
        incoming = open(stdin_path, 'rb') if stdin_path else open(os.devnull, 'rb')
        try:
            child = subprocess.Popen(command, stdout=out, stderr=err, stdin=incoming,
                                     cwd=directory, env=env, start_new_session=True, preexec_fn=limits)
            while True:
                pid, status, usage = os.wait4(child.pid, os.WNOHANG)
                if pid:
                    break
                if time.monotonic() - start > seconds:
                    timed_out = True
                    os.killpg(child.pid, signal.SIGKILL)
                    _, status, usage = os.wait4(child.pid, 0)
                    break
                time.sleep(0.01)
            child.returncode = os.waitstatus_to_exitcode(status)
        finally:
            incoming.close()
    data = {'command': command, 'exit_code': child.returncode, 'timeout': timed_out,
            'wall_seconds': time.monotonic() - start, 'user_seconds': usage.ru_utime,
            'system_seconds': usage.ru_stime, 'peak_rss_kib': usage.ru_maxrss,
            'address_space_limit_bytes': MEMORY,
            'memory_classification': 'no_automatic_OOM_inference_from_nonzero_exit'}
    save(directory / 'resources.json', data)
    return data


def worker(baseline, folder, request, name, optimized=False):
    request_path = folder / (name + '-request.json')
    save(request_path, request)
    flags = ['-I', '-S', '-B'] + (['-O'] if optimized else [])
    command = [sys.executable, *flags, str(HERE / 'worker.py'), str(baseline), str(request_path), str(folder / name)]
    return supervise(command, folder / (name + '-process'))


def native(baseline, folder, case, request, discovery):
    width = 32 if case['parameter_types'][0] == 'int' else 64
    engine_path = folder / 'discover/engine-result.json'
    engine = json.loads(engine_path.read_text()) if engine_path.exists() else {}
    witnesses = [row['input'] for row in engine.get('inner', {}).get('native_width_witnesses', [])]
    values = population(case['case_id'], width, witnesses)
    inputs = folder / 'native-inputs.txt'
    inputs.write_text(''.join(str(x) + '\n' for x in values))
    source = Path(request['source_path']).read_bytes().decode('utf-8')
    a, b = case['span']
    declaration = source[a:b]
    if hashlib.sha256(declaration.encode()).hexdigest() != case['declaration_sha256']:
        raise ValueError('native declaration identity')
    cast = '(int)' if width == 32 else ''
    harness = ('import java.io.*;\npublic final class NativeHarness {\n' + declaration +
               '\npublic static void main(String[] args) throws Exception {\n' +
               'BufferedReader in=new BufferedReader(new InputStreamReader(System.in));\n' +
               'String s; while((s=in.readLine())!=null) { try {\n' +
               'long raw=Long.parseUnsignedLong(s); System.out.println(' + case['method'] + '(' + cast + 'raw));\n' +
               '} catch(Throwable ex) {System.out.println("throws:"+ex.getClass().getName());}\n}\n}\n}\n')
    java = folder / 'NativeHarness.java'
    java.write_text(harness)
    flags = ['-Xmx256m', '-XX:+UseSerialGC', '-XX:CompressedClassSpaceSize=64m', '-XX:ReservedCodeCacheSize=64m', '-Xss256k']
    compile_metrics = supervise([shutil.which('javac'), *['-J' + f for f in flags], '--release', '17',
                                 '-proc:none', '-d', str(folder), str(java)], folder / 'native-compile', 60)
    if compile_metrics['exit_code'] != 0:
        return {'status': 'infrastructure_error', 'stage': 'native_compile', 'resources': compile_metrics}
    run_metrics = supervise([shutil.which('java'), *flags, '-cp', str(folder), 'NativeHarness'],
                             folder / 'native-execute', 120, inputs)
    if run_metrics['exit_code'] != 0:
        return {'status': 'infrastructure_error', 'stage': 'native_execute', 'resources': run_metrics}
    compare_request = {**request, 'mode': 'native_compare', 'inputs_path': str(inputs),
                       'native_stdout': str(folder / 'native-execute/stdout.log'), 'witness_inputs': witnesses}
    metrics = worker(baseline, folder, compare_request, 'native-compare', optimized=True)
    if metrics['exit_code'] != 0:
        return {'status': 'infrastructure_error', 'stage': 'native_compare', 'resources': metrics}
    compared = json.loads((folder / 'native-compare/result.json').read_text())
    valid = not compared['throws'] and not compared['source_ir_mismatches']
    if discovery['classification'] == 'certified':
        valid = valid and not compared['target_mismatches']
    return {'status': 'matched' if valid else 'correspondence_failure', **compared,
            'compile': compile_metrics, 'execution': run_metrics, 'comparison': metrics,
            'input_sha256': hashlib.sha256(inputs.read_bytes()).hexdigest(),
            'removed_annotations': [], 'scope': 'exact declaration in isolated class, not upstream project build'}


def run(baseline, data, output):
    from gate import preflight, verify_execution, snapshot, load_corpus
    baseline, data, output = [Path(x).resolve() for x in (baseline, data, output)]
    verify_execution()
    output.mkdir(parents=True, exist_ok=False)
    # Public corpus/runner identity and actual UTC are written before attempting
    # even a non-proof QKF applicability diagnostic.
    stamp = {'schema': 'qkf-run27-first-attempt-v1', 'utc_start': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'head': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
             'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
             'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'execution': json.loads((HERE / 'EXECUTION.json').read_text())}
    save(output / 'ATTEMPT.json', stamp)
    pre = preflight(baseline, data, require_runtime=True)
    save(output / 'preflight.json', pre)
    corpus = load_corpus()
    metadata = {f['source_file']: f for repo in corpus['source_frames'] for f in repo['files']}
    records = []
    fatal = []
    for case in corpus['cases']:
        folder = output / case['storage_id']
        folder.mkdir()
        request = {'mode': 'discover', 'case': case, 'source_path': str(data / case['source_file']),
                   'source_sha256': metadata[case['source_file']]['sha256'], 'budgets': corpus['budgets']}
        metrics = worker(baseline, folder, request, 'discover')
        result_path = folder / 'discover/result.json'
        if result_path.exists():
            row = json.loads(result_path.read_text())
        else:
            row = {'classification': 'budget_exhausted' if metrics['timeout'] else 'infrastructure_error',
                   'reason': 'wall_timeout' if metrics['timeout'] else 'missing_worker_result',
                   'source': {'status': 'not_attempted_or_unfinished'}}
        row.update(storage_id=case['storage_id'], discovery=metrics,
                   goal_registered=case['target'] is not None, replays=[],
                   native={'status': 'not_attempted', 'reason': 'source_not_accepted'})
        if row['classification'] in {'certified', 'refuted'}:
            proof = folder / 'discover/proof.json'
            if not proof.exists():
                fatal.append(case['storage_id'] + ': missing proof')
            else:
                row['proof_bytes'] = proof.stat().st_size
                row['proof_sha256'] = hashlib.sha256(proof.read_bytes()).hexdigest()
                for repeat in range(3):
                    name = 'replay-' + str(repeat)
                    replay_request = {**request, 'mode': 'replay', 'proof_path': str(proof)}
                    replay_metrics = worker(baseline, folder, replay_request, name, optimized=True)
                    same = (folder / name / 'engine-result.json').exists() and (folder / name / 'engine-result.json').read_bytes() == (folder / 'discover/engine-result.json').read_bytes()
                    row['replays'].append({'resources': replay_metrics, 'same_engine_result': same})
                    if replay_metrics['exit_code'] != 0 or not same:
                        fatal.append(case['storage_id'] + ': independent replay failure')
                times = [x['resources']['wall_seconds'] for x in row['replays']]
                row['replay_wall_summary'] = {'median': statistics.median(times), 'min': min(times), 'max': max(times)}
        if row.get('source', {}).get('status') == 'source_parsed':
            row['native'] = native(baseline, folder, case, request, row)
            if row['native']['status'] != 'matched':
                fatal.append(case['storage_id'] + ': native validation failure')
        if row['classification'] not in {'certified', 'refuted', 'unsupported', 'contract_unavailable', 'budget_exhausted'}:
            fatal.append(case['storage_id'] + ': ' + row['classification'])
        save(folder / 'RECORD.json', row)
        records.append(row)
    post = snapshot(baseline)
    if post != pre['baseline']:
        fatal.append('baseline changed during evaluation')
    save(output / 'postflight.json', post)
    counts = dict(collections.Counter(r['classification'] for r in records))
    sources = dict(collections.Counter(r.get('source', {}).get('status', 'not_attempted') for r in records))
    summary = {'schema': 'qkf-frozen-v3-evaluation-v1', 'status': 'accepted' if not fatal else 'incomplete',
               'denominator': len(corpus['cases']), 'counts': counts, 'source_stages': sources,
               'registered_goals': sum(c['target'] is not None for c in corpus['cases']),
               'errors': fatal, 'primary_timing_track': sys.version.startswith('3.12.'),
               'paired_v2': False, 'old_frozen_v2_result_unchanged': True,
               'native_inputs': sum(r['native'].get('inputs', 0) for r in records),
               'native_target_inputs': sum(r['native'].get('inputs', 0) for r in records if r['goal_registered']),
               'proofs': {r['storage_id']: r['proof_sha256'] for r in records if 'proof_sha256' in r},
               'record_files': [r['storage_id'] + '/RECORD.json' for r in records]}
    save(output / 'SUMMARY.json', summary)
    print(json.dumps(summary, sort_keys=True))
    return 0 if not fatal else 1


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit('usage: runner.py BASELINE INPUT NEW_OUTPUT')
    raise SystemExit(run(*sys.argv[1:]))
