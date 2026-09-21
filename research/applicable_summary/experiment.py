"""Registered functional run; save every outcome before acceptance assertions."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
from .contract import canonical, digest, load_json, save_json, require
from .fixtures import cases


def execute(case):
    from .producer import build
    from .checker import from_certificate
    source, r, mode = case['source'], case['request'], case['mode']
    if mode == 'build':
        # Accepted backends own exclusive profilers and already prohibit legacy
        # construction. The SDK separately guards export/pack/check after return.
        return build(source, r, route=case['route'], limits=case['limits'])
    begin = time.perf_counter_ns()
    if mode == 'import44':
        from research.source_lemmas.producer import prove
        proof, result, work = prove(source, r['query'], route=case['route'])
        kind = 'native_batch'
    elif mode == 'import41':
        from research.source_query.producer import prove
        proof, result, work = prove(source, r['query']['requests'][0])
        kind = 'source_query'
    else:
        from research.source_planner.producer import prove
        proof, result, work = prove(source, r['query']['requests'][0], fallback=mode == 'import_coverage')
        kind = 'source_plan'
        if mode == 'import_coverage':
            require(result['status'] == 'certified' and proof['kind'] == 'legacy'
                    and proof['evidence']['proof']['kind'] == 'covered', 'actual covered compatibility fixture')
    preparation = time.perf_counter_ns() - begin
    require(proof is not None, 'compatibility proof preparation')
    begin = time.perf_counter_ns()
    packet, result = from_certificate(source, r, proof, kind=kind)
    return packet, result, dict(compatibility_preparation_ns=preparation, compatibility_work=work,
                               import_and_check_ns=time.perf_counter_ns() - begin, kind=kind)


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    for name in ('PROTOCOL.json', 'REGISTRATION.json'):
        save_json(root / name, load_json(Path(__file__).with_name(name)))
    registration = load_json(root / 'REGISTRATION.json')
    require(digest(load_json(root / 'PROTOCOL.json')) == registration['protocol_sha256'], 'registered protocol')
    counts, packets, applications, failures, rows = Counter(), 0, 0, [], []
    from .checker import check
    from .audit import ExecutionGuard
    for case, registered in zip(cases(), registration['cases']):
        folder = root / case['name']; folder.mkdir()
        save_json(folder / 'case.json', case)
        try:
            require(case['name'] == registered['name'] and digest(case) == registered['case_sha256'], 'registered case')
            packet, result, work = execute(case)
            save_json(folder / 'outcome.json', dict(certificate=packet, result=result, work=work))
            require(result['status'] == case['expected'], 'registered outcome: ' + case['name'])
            applied = []
            if packet is not None:
                begin = time.perf_counter_ns()
                with ExecutionGuard(checking=True, witness=result['status'] == 'refuted') as guard:
                    checked = check(case['source'], case['request'], packet)
                cold = time.perf_counter_ns() - begin
                require(checked.result() == result, 'cold replay outcome')
                packets += 1
                with ExecutionGuard(checking=True, application=True):
                    for call in case['applications']:
                        begin = time.perf_counter_ns()
                        value = checked.apply(call['input'], width=call.get('width'))
                        elapsed = time.perf_counter_ns() - begin
                        require(type(value) is type(call['output']) and value == call['output'], 'checked apply')
                        applied.append(dict(value=value, elapsed_ns=elapsed)); applications += 1
                    checked.explain()
                rows.append(dict(name=case['name'], packet_bytes=len(canonical(packet).encode()),
                                 cold_check_ns=cold, cold_check_research_calls=guard.calls))
            save_json(folder / 'applications.json', applied)
            counts[result['status']] += 1
        except Exception as exc:
            failure = dict(case=case['name'], error=type(exc).__name__ + ': ' + str(exc), traceback=traceback.format_exc())
            failures.append(failure)
            save_json(folder / 'FAILURE.json', failure)
    semantic = dict(cases=len(registration['cases']), packets=packets, applications=applications, statuses=dict(counts))
    summary = dict(semantic=semantic, measurements=rows, failures=len(failures))
    save_json(root / 'SUMMARY.json', summary); save_json(root / 'FAILURES.json', failures)
    manifest = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(root.rglob('*')) if p.is_file()}
    save_json(root / 'MANIFEST.json', manifest)
    require(not failures, 'functional failures retained in ' + str(root))
    return summary


if __name__ == '__main__':
    print(json.dumps(run(Path(sys.argv[1])), sort_keys=True))
