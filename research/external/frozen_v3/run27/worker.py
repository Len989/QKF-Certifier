"""One isolated measured operation. Only the frozen export supplies QKF code.

The caller verifies registration, source identities and runtime before launching
this worker. No executable text is supplied by a certificate or source file.
"""
import hashlib
import json
from pathlib import Path
import sys
import traceback


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True, separators=(',', ':'), allow_nan=False)
        stream.write('\n')


def install_guard(replay):
    class Guard:
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split('.')[0] in {'subprocess', 'z3', 'cvc5', 'pysmt'} or (replay and 'producer' in fullname):
                raise ImportError('forbidden worker dependency: ' + fullname)
            return None
    sys.meta_path.insert(0, Guard())
    def audit(event, args):
        if event == 'subprocess.Popen' or event == 'os.system' or event.startswith(('os.exec', 'os.spawn')):
            raise RuntimeError('native execution forbidden in worker')
    sys.addaudithook(audit)


def read_ir(source, case):
    route = case['source_diagnostic_route']
    entry = {'class': case['class'], 'method': case['method']}
    if route == 'signed':
        from research.signed_predicates.frontend import read_source
        ir = read_source(source, entry, case['parameter_types'][0])
    elif route == 'word_long':
        from research.wordexpr.frontend import read_source
        ir = read_source(source, entry)
    else:
        return None
    if ir['span'] != case['span'] or ir['declaration_sha256'] != case['declaration_sha256']:
        raise ValueError('independent declaration inventory disagrees with QKF selection')
    return ir


def execute(request, output):
    case = request['case']
    raw = Path(request['source_path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != request['source_sha256']:
        raise ValueError('worker source identity')
    source = raw.decode('utf-8')
    mode = request['mode']
    if mode == 'replay':
        from research.unified.v3 import check
        proof = json.loads(Path(request['proof_path']).read_text())
        result = check(source, case['target'], proof)
        save(output / 'engine-result.json', result)
        return {'classification': result['status'], 'case_id': case['case_id']}
    from research.wordexpr.frontend import Unsupported
    if mode == 'discover':
        try:
            ir = read_ir(source, case)
            diagnostic = {'status': 'no_source_profile'} if ir is None else {
                'status': 'source_parsed', 'ir_sha256': hashlib.sha256(json.dumps(
                    ir, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                'node_count': len(ir['nodes'])}
            if ir is not None:
                save(output / 'source-ir.json', ir)
        except Unsupported as exc:
            diagnostic = {'status': 'source_unsupported', 'reason': str(exc)}
        state = case['contract_state']
        row = {'case_id': case['case_id'], 'source': diagnostic, 'classification': state,
               'reason': 'no_supported_target_language' if state == 'unsupported' else state}
        if case['target'] is not None:
            from research.unified.v3 import prove
            result, proof = prove(source, case['target'], budgets=request['budgets'])
            save(output / 'engine-result.json', result)
            row.update(classification=result['status'], reason=result.get('inner', {}).get('reason'))
            if proof is not None:
                save(output / 'proof.json', proof)
        return row
    if mode != 'native_compare':
        raise ValueError('unknown worker operation')
    ir = read_ir(source, case)
    if ir is None:
        raise ValueError('native correspondence requires an accepted source IR')
    if case['source_diagnostic_route'] == 'signed':
        from research.signed_predicates.semantics import evaluate
    else:
        from research.wordexpr.semantics import evaluate
    width = 32 if case['parameter_types'][0] == 'int' else 64
    inputs = [int(x) for x in Path(request['inputs_path']).read_text().splitlines()]
    actual = Path(request['native_stdout']).read_text().splitlines()
    if len(actual) != len(inputs):
        raise ValueError('native output population mismatch')
    mismatches, target_mismatches, throws = [], [], []
    expected_target = case['target'] is not None
    # This independent whole-integer specification is NOT the source bit trick.
    if expected_target and case['target']['goal'] != ['and', ['positive'], ['popcount_eq', 1]]:
        raise ValueError('native target oracle is not registered for this goal')
    witness_results = []
    for x, encoded in zip(inputs, actual):
        if encoded.startswith('throws:'):
            throws.append({'input': x, 'exception': encoded[7:]})
            continue
        if case['return_type'] == 'boolean':
            if encoded not in {'true', 'false'}:
                raise ValueError('invalid native Boolean')
            y = encoded == 'true'
        else:
            y = int(encoded) & ((1 << width) - 1)
        expected_ir = evaluate(ir, x, width)
        if type(y) is not type(expected_ir) or y != expected_ir:
            mismatches.append({'input': x, 'java': y, 'ir': expected_ir})
        target_value = x != 0 and x < (1 << (width - 1)) and x.bit_count() == 1
        if expected_target and y != target_value:
            target_mismatches.append({'input': x, 'java': y, 'target': target_value})
        if x in request.get('witness_inputs', []):
            witness_results.append({'input': x, 'java': y, 'ir': expected_ir,
                                    'target': target_value if expected_target else None})
    return {'case_id': case['case_id'], 'width': width, 'inputs': len(inputs),
            'source_ir_mismatches': mismatches, 'target_mismatches': target_mismatches if expected_target else None,
            'throws': throws, 'witness_results': witness_results,
            'target_status': 'compared' if expected_target else 'not_registered',
            'scope': 'finite physical-width implementation correspondence, not a universal proof'}


def main():
    if len(sys.argv) != 4:
        raise SystemExit('usage: worker.py BASELINE REQUEST OUTPUT')
    baseline, request_path, output = map(Path, sys.argv[1:])
    baseline, output = baseline.resolve(), output.resolve()
    request = json.loads(request_path.read_text())
    output.mkdir(parents=True, exist_ok=False)
    # -I -S drops cwd, user site and PYTHONPATH. The only extra module root is
    # the byte-verified baseline, not the evaluator checkout or candidate source.
    sys.path.insert(0, str(baseline))
    install_guard(request['mode'] != 'discover')
    code = 0
    try:
        result = execute(request, output)
    except MemoryError:
        result = {'classification': 'budget_exhausted', 'reason': 'MemoryError_under_2GiB_RLIMIT_AS'}
        code = 2
    except Exception as exc:
        traceback.print_exc()
        result = {'classification': 'invalid_certificate' if request['mode'] == 'replay' else 'internal_error',
                  'error_type': type(exc).__name__, 'error': str(exc)}
        code = 3 if request['mode'] == 'replay' else 70
    origins = {}
    for name, module in sorted(sys.modules.items()):
        if name == 'research' or name.startswith('research.') or name.startswith('qkf_certifier'):
            path = getattr(module, '__file__', None)
            if path:
                p = Path(path).resolve()
                if baseline not in p.parents:
                    raise RuntimeError('QKF module loaded outside isolated baseline: ' + str(p))
                origins[name] = {'path': str(p.relative_to(baseline)),
                                 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
    save(output / 'origins.json', {'modules': origins, 'sys_path': sys.path,
                                  'python': sys.version, 'mode': request['mode']})
    save(output / 'result.json', result)
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
