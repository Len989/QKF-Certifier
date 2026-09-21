"""Artifact identities, denominators and deterministic schedules (no search imports)."""
import hashlib
from pathlib import Path
from research.semantic_work.contract import canonical, digest, load_json, save_json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def checkpoint_json(path, value):
    """Atomically replace only a live run ledger; evidence files use exclusive save_json."""
    temporary = path.with_name(path.name + '.pending')
    temporary.write_text(canonical(value) + '\n', encoding='utf-8')
    temporary.replace(path)


def require(value, message):
    if not value:
        raise ValueError(message)


def registered():
    protocol = load_json(HERE / 'PROTOCOL.json')
    reg = load_json(HERE / 'REGISTRATION.json')
    require(digest(protocol) == reg['protocol_sha256'], 'registered protocol changed')
    return protocol, reg


def validate_case(case, entry):
    require(digest(case) == entry['case_sha256'] and case['name'] == entry['name'],
            'registered source/request/limits/outcome changed')
    require(case['routes'] == entry['routes'] and case['unavailable'] == entry['unavailable'], 'route population')
    require(case['expected'] == entry['expected'], 'expected outcomes')


def schedule(routes, index, trial):
    shift = (index + trial) % len(routes)
    order = routes[shift:] + routes[:shift]
    return list(reversed(order)) if trial % 2 else order


def identity(saved):
    return dict(certificate_sha256=None if saved['certificate'] is None else digest(saved['certificate']),
                result_sha256=digest(saved['result']), status=saved['result']['status'])


def compare_identity(saved, trial):
    require(identity(saved) == trial['identity'], 'timed certificate/result changed')


def backend(saved):
    work = saved['work']
    return work.get('backend', work)


def matched_verdicts(outcomes):
    """A nonconsequence or budget is not a negative source verdict."""
    values = {x for x in outcomes if x in ('certified', 'refuted')}
    require(len(values) <= 1, 'completed source verdicts disagree on the same obligation')


def validate_attempts(attempts, reg, repetitions):
    expected = {(c['name'], route, str(trial), operation)
                for c in reg['cases'] for route in c['routes'] if route not in c['unavailable']
                for trial in ['audit'] + list(range(repetitions)) for operation in ('build', 'check')}
    expected.update((c['name'], route, 'memory', 'build') for c in reg['cases']
                    for route in c['routes'] if route not in c['unavailable'])
    actual = [(a['case'], a['route'], str(a['trial']), a['operation']) for a in attempts]
    require(len(actual) == len(expected) and set(actual) == expected, 'complete unique build/check attempt denominator')


def inventory(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'MANIFEST.json'}


def check_inventory(root):
    paths = list(root.rglob('*'))
    require(not root.is_symlink() and not any(p.is_symlink() for p in paths), 'artifact symlink')
    manifest = load_json(root / 'MANIFEST.json')
    require(type(manifest) is dict and set(manifest) ==
            {str(p.relative_to(root)) for p in paths if p.is_file()} - {'MANIFEST.json'}, 'artifact file set')
    for name, expected in manifest.items():
        p = Path(name)
        require(not p.is_absolute() and '..' not in p.parts, 'artifact path')
        require(hashlib.sha256((root / p).read_bytes()).hexdigest() == expected, 'artifact bytes: ' + name)


def metrics(values):
    require(values and all(type(x) is int and x >= 0 for x in values), 'nonnegative integer measurements')
    ordered = sorted(values)
    return dict(samples=values, median=ordered[len(values) // 2], minimum=ordered[0], maximum=ordered[-1])
