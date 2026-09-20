"""Registered control experiment. Every child and failure is retained; no automatic retries."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from .contract import canonical, digest, load_json, save_json, request

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent


class TimingOnly:
    """No tracer in timing trials. Only old per-route ceilings and parent timeout apply."""
    def stage(self, name, **kwargs):
        from contextlib import nullcontext
        return nullcontext({})
    def note_fallback(self):
        pass


def worker(mode, path, out):
    r = load_json(path)
    start = time.perf_counter_ns()
    if mode == 'audit':
        from .run import run
        record = run(r, forbid_full=True)
    else:
        r = request(r)
        if mode == 'direct':
            if r['conditions']:
                result, proof = {'status': 'unsupported_conditions'}, None
            else:
                from research.unified.v6 import prove
                result, proof = prove(r['source'], r['consumer']['target'], budgets=r['budget']['backend'])
        else:
            from .run import execute
            outcome, envelope = execute(r, TimingOnly())
            result = outcome.get('legacy_result', outcome)
            proof = None if envelope is None else envelope['legacy']
        record = {'status': result['status'], 'legacy_result_sha256': digest(result),
                  'legacy_proof_sha256': None if proof is None else digest(proof),
                  'api_elapsed_ns': time.perf_counter_ns() - start,
                  'global_call_limit_enforced': False,
                  'limits_scope': 'old backend caps; parent wall timeout; no tracer in timing trials'}
    save_json(out, record)


def child(mode, req, out, root):
    started = time.perf_counter_ns()
    command = [sys.executable, '-B', '-m', 'research.semantic_work.experiment',
               '--worker', mode, str(req), str(out)]
    try:
        p = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)
        result = {'mode': mode, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}
    except subprocess.TimeoutExpired as exc:
        def text(x):
            return x.decode(errors='replace') if type(x) is bytes else (x or '')
        result = {'mode': mode, 'returncode': None, 'timeout': True,
                  'stdout': text(exc.stdout), 'stderr': text(exc.stderr)}
    result['process_elapsed_ns'] = time.perf_counter_ns() - started
    save_json(root / (out.name + '.process.json'), result)
    return result


def run_experiment(root):
    from .fixtures import cases
    root.mkdir(parents=True, exist_ok=False)
    protocol = load_json(HERE / 'PROTOCOL.json')
    registration = load_json(HERE / 'REGISTRATION.json')
    rows = list(cases())
    expected = [{'name': n, 'request_sha256': digest(r)} for n, r in rows]
    if expected != registration['cases']:
        raise ValueError('registered requests changed')
    save_json(root / 'PROTOCOL.json', protocol)
    save_json(root / 'REGISTRATION.json', registration)
    summary, failures = [], []
    for i, (name, r) in enumerate(rows):
        print('semantic-work case', i, name, file=sys.stderr, flush=True)
        directory = root / ('case-%02d' % i)
        directory.mkdir()
        save_json(directory / 'request.json', r)
        mixed = json.loads(canonical(r));mixed['strategy'] = 'witness_then_covered'
        save_json(directory / 'mixed-request.json', mixed)
        outputs = {}
        for mode, req_name, out_name in (
            ('direct','request.json','direct.json'),
            ('audit','request.json','covered.json'),
            ('audit','mixed-request.json','mixed.json')):
            process = child(mode, directory/req_name, directory/out_name, directory)
            if process['returncode'] != 0:
                failures.append({'case': name, 'output': out_name, 'process': process})
                continue
            outputs[out_name] = load_json(directory/out_name)
        row = {'name': name, 'statuses': {}}
        if len(outputs) == 3:
            direct = outputs['direct.json'];covered = outputs['covered.json'];mixed_out = outputs['mixed.json']
            row['statuses'] = {'direct': direct['status'], 'covered': covered['result']['status'],
                               'mixed': mixed_out['result']['status']}
            if direct['status'] != row['statuses']['covered']:
                failures.append({'case': name, 'error': 'direct/control status differs'})
            if covered['proof'] is not None:
                if digest(covered['proof']['legacy']) != direct['legacy_proof_sha256']:
                    failures.append({'case': name, 'error': 'legacy proof differs'})
            for label, value in (('covered',covered),('mixed',mixed_out)):
                if value['proof'] is not None:
                    save_json(directory / (label+'-proof.json'), value['proof'])
            if direct['status'] in ('certified','refuted') and row['statuses']['mixed'] in ('certified','refuted'):
                if direct['status'] != row['statuses']['mixed']:
                    failures.append({'case': name, 'error': 'completed routes disagree'})
        for repeat in range(protocol['measurement']['timing_repeats']):
            order = ('direct','wrapped') if repeat % 2 == 0 else ('wrapped','direct')
            for arm in order:
                out = directory / ('timing-%d-%s.json' % (repeat,arm))
                process = child(arm, directory/'request.json', out, directory)
                if process['returncode'] != 0:
                    failures.append({'case': name, 'trial': out.name, 'process': process})
                elif 'direct.json' in outputs:
                    t = load_json(out)
                    d = outputs['direct.json']
                    if t['status'] != d['status'] or t['legacy_proof_sha256'] != d['legacy_proof_sha256']:
                        failures.append({'case': name, 'trial': out.name, 'error': 'timed outcome/proof differs'})
        summary.append(row)
    save_json(root / 'FAILURES.json', failures)
    result = {'schema': 'qkf-semantic-control-summary-v1', 'cases': summary,
              'presentations': len(rows), 'failed_attempts': len(failures),
              'status': 'failed' if failures else 'passed', 'new_semantic_claim': False,
              'timing_trials': len(rows)*protocol['measurement']['timing_repeats']*2}
    save_json(root / 'SUMMARY.json', result)
    manifest = {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(root.rglob('*')) if p.is_file()}
    save_json(root/'MANIFEST.json', manifest)
    if failures:
        raise RuntimeError('recorded experiment failures; see FAILURES.json')
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',choices=('audit','direct','wrapped'))
    parser.add_argument('path',type=Path)
    parser.add_argument('out',type=Path,nargs='?')
    args=parser.parse_args()
    if args.worker:
        worker(args.worker,args.path,args.out)
    else:
        print(canonical(run_experiment(args.path)))
