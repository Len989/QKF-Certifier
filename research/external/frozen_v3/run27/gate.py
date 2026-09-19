"""Data/identity gates for Run27. This module never imports a QKF proof engine."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import stat
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASE = 'c8c7b4eeaf848d31c8c324a4316ffec8aac81cda'
TREE = '4838b8badbb3a56f8a7d2a197ce6c0d3d6b3a77d'
INVENTORY = '22c113ee8a14df0dcbe6014ae398d4ea97a7a20b027d0775fd162503af18b9b4'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load(path):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, 'duplicate JSON key: ' + key)
            out[key] = value
        return out
    def reject(x):
        raise ValueError('nonfinite JSON: ' + x)
    return json.loads(Path(path).read_text(), object_pairs_hook=unique, parse_constant=reject)


def load_corpus():
    corpus = load(HERE / 'CORPUS.json')
    cases = []
    for name, expected in corpus['case_files'].items():
        path = HERE / name
        require(path.parent == HERE and not path.is_symlink(), 'corpus part path')
        require(sha(path.read_bytes()) == expected, 'corpus part identity')
        cases.extend(json.loads(line) for line in path.read_text().splitlines())
    cases.sort(key=lambda row: row['storage_id'])
    serialized = json.dumps(cases, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    require(sha(serialized) == corpus['case_inventory_sha256'], 'full case inventory identity')
    corpus['cases'] = cases
    return corpus


def snapshot(path):
    # Explicit metadata verifier, NOT import of a second QKF implementation.
    spec = importlib.util.spec_from_file_location('frozen_metadata', HERE.parent / 'verify.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    identity = module.snapshot(path)
    require(identity == {'git_tree': TREE, 'file_count': 1837, 'total_bytes': 30048148,
                         'inventory_sha256': INVENTORY}, 'frozen baseline identity changed')
    return identity


def verify_seals():
    lock = load(HERE / 'CORPUS_LOCK.json')
    require(lock['schema'] == 'qkf-run27-corpus-lock-v1' and lock['baseline_commit'] == BASE,
            'corpus lock identity')
    require(lock['acquisition_commit'] == '646aabb66b531391d09995bf028e9b414443a9b7', 'acquisition gate')
    for relative, expected in lock['files_sha256'].items():
        path = ROOT / relative
        require(not path.is_symlink() and ROOT in path.resolve().parents, 'unsafe locked file')
        require(sha(path.read_bytes()) == expected, 'corpus/runner seal: ' + relative)
    corpus = load_corpus()
    require(corpus['schema'] == 'qkf-frozen-v3-corpus-v1' and corpus['baseline_commit'] == BASE,
            'corpus identity')
    require(corpus['denominator'] == len(corpus['cases']) == 33, 'complete denominator')
    require(corpus['frame_files'] == sum(len(r['files']) for r in corpus['source_frames']) == 24,
            'complete frame')
    require(corpus['budgets'] == {'max_features': 128, 'max_target_states': 8192}, 'unchanged budgets')
    require(len({r['case_id'] for r in corpus['cases']}) == 33, 'distinct canonical IDs')
    require([r['storage_id'] for r in corpus['cases']] == ['m%03d' % i for i in range(1, 34)], 'ordered cases')
    for case in corpus['cases']:
        require(case['contract_state'] in {'registered_goal', 'unsupported', 'contract_unavailable'}, 'contract status')
        require((case['target'] is not None) == (case['contract_state'] == 'registered_goal'), 'target/contract gate')
        if case['target'] is not None:
            require(case['doc_span'] is not None and case['extension'], 'documented independent goal')
    return corpus


def verify_execution():
    verify_seals()
    execution = load(HERE / 'EXECUTION.json')
    require(execution['schema'] == 'qkf-run27-execution-authorization-v1', 'execution schema')
    require(execution['corpus_lock_sha256'] == sha((HERE / 'CORPUS_LOCK.json').read_bytes()), 'execution lock')
    commit = execution['corpus_commit']
    require(type(commit) is str and len(commit) == 40, 'published corpus commit')
    # The record points at a prior committed lock, not a retrospective timestamp.
    raw = subprocess.check_output(['git', '-C', str(ROOT), 'show',
                                   commit + ':research/external/frozen_v3/run27/CORPUS_LOCK.json'])
    require(sha(raw) == execution['corpus_lock_sha256'], 'committed corpus lock differs')
    subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', commit, 'HEAD'], check=True)
    return execution


def runtime_check():
    from acquire import runtime
    actual = runtime()
    registered = load(HERE / 'RUNTIMES.json').get(platform.python_version())
    require(registered is not None, 'unregistered Python version')
    # Paths/host kernel are recorded, but are not binary identity. These fields
    # fix the executable/runtime builds and hosted image before any candidate.
    keys = ['python', 'python_version', 'python_executable_sha256', 'python_config',
            'java_release', 'java_sha256', 'javac_sha256', 'java_modules_sha256',
            'java_version', 'javac_version', 'os_release', 'machine', 'image_os', 'image_version']
    for key in keys:
        require(actual[key] == registered[key], 'runtime drift: ' + key)
    return actual


def verify_inputs(corpus, data, with_inventory=True):
    data = Path(data).resolve()
    require(sha((data / 'FRAME.json').read_bytes()) == corpus['frame_sha256'], 'complete frame identity')
    for repo in corpus['source_frames']:
        for item in repo['files'] + repo['licenses']:
            path = data / item['source_file']
            require(not path.is_symlink() and data in path.resolve().parents, 'unsafe acquired path')
            raw = path.read_bytes()
            require(len(raw) == item['size'] and sha(raw) == item['sha256'], 'source bytes: ' + str(path))
            blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            require(blob == item['git_blob'], 'pinned source blob')
    for case in corpus['cases']:
        text = (data / case['source_file']).read_bytes().decode('utf-8')
        for span_key, hash_key in [('span','declaration_sha256'), ('body_span','body_sha256'), ('doc_span','doc_sha256')]:
            bounds = case[span_key]
            if bounds is None:
                require(case[hash_key] is None, 'absent span identity')
            else:
                a,b = bounds
                require(type(a) is int and type(b) is int and 0 <= a < b <= len(text), 'valid source span')
                require(sha(text[a:b].encode()) == case[hash_key], 'source/documentation span')
    if with_inventory:
        from inventory import inventory, canonical
        rows, diagnostics = inventory(data)
        obj = {'declarations': rows, 'diagnostics': diagnostics}
        serialized = canonical(obj)
        require(sha(serialized) == corpus['declaration_inventory_sha256'], 'independent declaration inventory')
        stored = data / 'DECLARATIONS.json'
        if stored.exists():
            require(stored.read_bytes() == serialized, 'retained inventory changed')
        else:
            with stored.open('xb') as stream:
                stream.write(serialized)
        selected = [r for r in rows if r['eligible']]
        require(len(rows) == 1457 and len(selected) == 33, 'inventory denominator')
        keys = ('source_file','class','method','return_type','parameter_types','span','body_span',
                'declaration_sha256','body_sha256','normalized_body_sha256','doc_span','doc_sha256')
        require(all(all(a[k] == b[k] for k in keys) for a,b in zip(selected, corpus['cases'])), 'registered methods differ from inventory')
        return obj
    return None


def preflight(baseline, data, require_runtime=True):
    corpus = verify_seals()
    identity = snapshot(baseline)
    current = runtime_check() if require_runtime else None
    inv = verify_inputs(corpus, data)
    return {'schema': 'qkf-run27-preflight-v1', 'baseline': identity,
            'runtime': current, 'denominator': corpus['denominator'],
            'inventory_records': len(inv['declarations']),
            'corpus_sha256': sha((HERE / 'CORPUS.json').read_bytes()),
            'lock_sha256': sha((HERE / 'CORPUS_LOCK.json').read_bytes())}


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3:
        raise SystemExit('usage: gate.py ISOLATED_BASELINE ACQUIRED_INPUT')
    print(json.dumps(preflight(sys.argv[1], sys.argv[2]), sort_keys=True))
