"""Recompute every denominator, lifecycle row and registered baseline choice."""
from collections import Counter
from .common import (load_json, require, registered, validate_case, validate_attempts,
                     compare_identity, identity, metrics, canonical, digest)


def analyze(root):
    shard = load_json(root / 'RUN.json')['shard']
    protocol, reg = registered(shard)
    repeats = protocol['measurement']['timing_repeats']
    attempts = load_json(root / 'ATTEMPTS.json')
    validate_attempts(attempts, reg, repeats)
    require(all(a['status'] == 'passed' for a in attempts) and not load_json(root / 'FAILURES.json'),
            'failed attempts remain in denominator')
    rows, outcomes = [], Counter()
    packets = checkpoints = applications = 0
    for entry in reg['cases']:
        folder = root / entry['name']
        case = load_json(folder / 'case.json')
        validate_case(case, entry)
        for route in entry['routes']:
            path = folder / route
            audit = load_json(path / 'audit.json')
            require(identity(audit) == audit['identity'], 'audit identity')
            require(audit['result']['status'] == entry['expected'][route], 'registered outcome')
            checked = load_json(path / 'audit-check.json')
            require(checked['status'] == 'passed' and checked['search_imports'] == 0, 'independent receiver')
            memory = load_json(path / 'memory.json')
            compare_identity(audit, memory)
            builds, receivers, processes = [], [], []
            for trial in range(repeats):
                build = load_json(path / f'timing-{trial}.json')
                receiver = load_json(path / f'timing-{trial}-check.json')
                compare_identity(audit, build)
                require(canonical(receiver['semantic']) == canonical(checked['semantic']), 'receiver semantic identity')
                builds.append(build)
                receivers.append(receiver)
                process_pair = [load_json(path / f'timing-{trial}{suffix}.process.json') for suffix in ('', '-check')]
                require(all(p['returncode'] == 0 and not p['timeout'] for p in process_pair), 'timing child failed')
                processes.append(sum(p['process_elapsed_ns'] for p in process_pair))
            packets += checked['packets']
            checkpoints += checked['checkpoints']
            applications += checked['warm_apply_calls']
            outcomes[audit['result']['status']] += 1
            row = dict(case=case['name'], group=case['group'], family=case['family'], route=route,
                       delivery=audit['delivery'], status=audit['result']['status'],
                       goals=len(case['request']['query'].get('requests', case['request']['query'].get('goals', []))),
                       width=case['request']['query'].get('requests', [{}])[0].get('width'),
                       members=audit['member_count'], packets=checked['packets'], checkpoints=checked['checkpoints'],
                       certificate_bytes=audit['certificate_bytes'], native_packet_bytes=audit['native_packet_bytes'],
                       request_bytes=audit['request_bytes'], source_bytes=audit['source_bytes'],
                       python_peak_bytes=memory['traced_peak_bytes'], calls=audit['trace']['counts'],
                       code_calls=audit['trace']['calls'],
                       build_ns=metrics([b['build_ns'] for b in builds]),
                       cold_check_ns=metrics([c['cold_check_ns'] for c in receivers]),
                       assess_ns=metrics([c['assess_ns'] for c in receivers]),
                       export_explain_ns=metrics([c['export_explain_ns'] for c in receivers]),
                       lifecycle_ns=metrics([b['build_ns'] + c['lifecycle_receiver_ns'] for b, c in zip(builds, receivers)]),
                       whole_process_pair_ns=metrics(processes),
                       application_status=checked['application_status'],
                       warm_apply_ns=None if receivers[0]['warm_apply_ns'] is None else metrics([c['warm_apply_ns'] for c in receivers]),
                       lifecycle_plus_apply_ns=None if receivers[0]['warm_apply_ns'] is None else metrics([
                           b['build_ns'] + c['lifecycle_receiver_ns'] + c['warm_apply_ns'] for b, c in zip(builds, receivers)]),
                       semantic=checked['semantic'],
                       emission=[w.get('backend', w).get('emission') for w in audit['work']['members']],
                       diagnostic_bytes=audit['diagnostic_bytes'])
            rows.append(row)
        for route in entry['routes']:
            if 'emitted_' not in route:
                continue
            previous = route.replace('emitted_', 'prepared_', 1)
            new = load_json(folder / route / 'audit.json')
            old = load_json(folder / previous / 'audit.json')
            compare_identity(new, old)
            for new_work, old_work in zip(new['work']['members'], old['work']['members']):
                a, b = new_work['backend'], old_work['backend']
                require(canonical(a['fact_attempts']) == canonical(b['fact_attempts']), 'matched native questions changed')
                require(canonical(a['foundations']) == canonical(b['foundations']), 'matched checked foundations changed')
                require([r['id'] for r in a['checkpoints']] == [r['id'] for r in b['checkpoints']],
                        'matched actual intermediate obligations changed')
    baseline = {'single_summary': 'sdk_ordinary', 'consumer_service': 'once_ordinary',
                'independent_certificates': 'each_ordinary'}
    return dict(schema='qkf-direct-emission-cost-summary-v1', shard=shard, cases=len(reg['cases']),
                pairs=len(rows), attempts=len(attempts), failures=0, timing_repeats=repeats,
                protocol_sha256=reg['protocol_sha256'],
                semantic=dict(packets=packets, checkpoints=checkpoints, applications=applications, statuses=dict(outcomes)),
                baselines=baseline, rows=rows, economic_claim='instrumented development costs for registered equal deliveries',
                F1='open', algorithms_changed=False, preparation_changed=True, direct_export=True)
