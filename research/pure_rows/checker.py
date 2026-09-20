"""Standalone checker for exact typed-ground pure-row initial semantics.

No producer, prototype, search, SMT, native execution, or signed profile imports.
A certificate carries structural feedback, generated-domain/kernel evidence,
chronological interface derivations and total separating models at horizons 1,2.
"""
from __future__ import annotations
import itertools
from .common import (CERTIFICATE, RESULT, THEORY, InvalidCertificate, blocks, canonical,
                     digest, encoded, fields, integer, lift_seeds, need, partition,
                     presentation, quotient, records, snapshot, value)
from .closure import check_closure
from .geometry import verify_geometry
from .model import verify_model


def interface_data(p: dict, horizon: int) -> tuple:
    n, nb = len(p['carrier']['names']), len(p['operators']['names'])
    return (n * (nb + 1), records(n, p['carrier']['operations'], 1 if horizon == 1 else nb + 1),
            [((b + 1) * n + a, c) for b, a, c in p['cells']], (n, nb))


def _check(p: dict, cert: dict) -> dict:
    fields(cert, ('schema', 'input_sha256', 'feedback', 'rows', 'levels', 'result'))
    need(cert['schema'] == CERTIFICATE and cert['input_sha256'] == digest(p), 'input/certificate binding')
    n, nb = len(p['carrier']['names']), len(p['operators']['names'])
    ops = p['carrier']['operations']
    stages = cert['feedback']
    need(type(stages) is list and 1 <= len(stages) <= n, 'feedback round bound')
    theta = list(range(n))
    trajectory = [theta]
    for index, stage in enumerate(stages):
        fields(stage, ('carrier_partition', 'pushouts', 'join'))
        need(encoded(stage['carrier_partition']) == encoded(theta), 'feedback must start at diagonal and be consecutive')
        qn, qops = quotient(n, ops, theta)
        need(type(stage['pushouts']) is list and len(stage['pushouts']) == nb, 'missing row pushout')
        kernels = []
        for b, local in enumerate(stage['pushouts']):
            seeds = [(qn + theta[a], theta[c]) for bb, a, c in p['cells'] if bb == b]
            local_partition = check_closure(2 * qn, records(qn, qops, 2), seeds, local)
            kernels.append(canonical(local_partition[:qn]))
        nxt = check_closure(n, records(n, ops), lift_seeds(theta, kernels), stage['join'])
        if index + 1 == len(stages):
            need(nxt == theta, 'last feedback round is not a common fixed point')
        else:
            need(nxt != theta and len(set(nxt)) < len(set(theta)), 'non-strict intermediate feedback round')
            trajectory.append(nxt)
        theta = nxt
    qn, qops = quotient(n, ops, theta)
    need(type(cert['rows']) is list and len(cert['rows']) == nb, 'row geometry missing')
    predicted = [('central', a) for a in theta]
    row_results = []
    for b, row in enumerate(cert['rows']):
        cells = [(theta[a], theta[c]) for bb, a, c in p['cells'] if bb == b]
        h, kappa, forced, external = verify_geometry(qn, qops, cells, row)
        for qa in theta:
            predicted.append(('central', forced[qa]) if forced[qa] is not None else ('external', b, kappa[qa]))
        domain = [x for x, y in enumerate(h) if y is not None]
        image = sorted({h[x] for x in domain})
        kernel_on_domain = [[x for x in domain if h[x] == y] for y in image]
        row_results.append(dict(operator=b, generated_domain=domain,
                                homomorphism=[[x, h[x]] for x in domain],
                                kernel_on_generated_domain=kernel_on_domain,
                                ambient_kernel=blocks(kappa),
                                forced_domain=[x for x, y in enumerate(forced) if y is not None],
                                forced_values=forced, external_classes=external,
                                external_count=len(external)))
    need(type(cert['levels']) is list and len(cert['levels']) == 2, 'both interface horizons required')
    partitions = []
    counts = []
    evaluations = []
    for h, level in enumerate(cert['levels'], 1):
        fields(level, ('horizon', 'equality', 'model'))
        need(type(level['horizon']) is int and level['horizon'] == h, 'incorrect horizon')
        size, native, seeds, feedback = interface_data(p, h)
        labels = check_closure(size, native, seeds, level['equality'], feedback)
        evaluations.append(verify_model(p, level['model'], h, labels))
        partitions.append(labels)
        counts.append(len(set(labels)))
    first, final = partitions
    need(final == canonical(predicted), 'global interface differs from protected row geometry')
    need(canonical(final[:n]) == theta, 'structural and direct carrier quotients disagree')
    theta1 = canonical(first[:n])
    q1, _ = quotient(n, ops, theta1)
    first_prediction = [('central', a) for a in theta1]
    count1 = q1
    for b in range(nb):
        supplied = {}
        for bb, a, c in p['cells']:
            if bb == b:
                key, image = theta1[a], theta1[c]
                need(key not in supplied or supplied[key] == image, 'horizon-one value incoherence')
                supplied[key] = image
        first_prediction.extend(('central', supplied[a]) if a in supplied else ('external', b, a) for a in theta1)
        count1 += q1 - len(supplied)
    need(first == canonical(first_prediction) and counts[0] == count1, 'horizon-one structural formula')
    need(counts[1] == qn + sum(r['external_count'] for r in row_results), 'horizon-two class count')
    # Nested restrictions are checked explicitly rather than inferred just from counts.
    for block in blocks(first):
        need(len({final[x] for x in block}) == 1, 'horizon relations not nested')
    contacts = []
    for b in range(nb):
        contacts.append([1 if first[(b + 1) * n + a] in set(first[:n]) else
                         2 if final[(b + 1) * n + a] in set(final[:n]) else None for a in range(n)])
    result = dict(schema=RESULT, status='certified', claim='exact_named_initial_interface',
                  theory=THEORY, input_sha256=digest(p),
                  carrier_partition=blocks(theta), carrier_protected=(qn == n),
                  quotient_size=qn, quotient_operations=qops,
                  rows=row_results, feedback_trajectory=[blocks(x) for x in trajectory],
                  strict_feedback_rounds=len(stages) - 1,
                  interface=dict(order='carrier names, then row-major alpha(b,a)',
                                 horizon1_partition=blocks(first), horizon2_partition=blocks(final),
                                 N1=counts[0], N2=counts[1],
                                 stabilization_horizon=1 if first == final else 2,
                                 carrier_contact_horizons=contacts),
                  evaluated_model_axioms=evaluations,
                  completion_checked=False, lean_checked=False,
                  scope='two-sorted named-input ground diagrams and independent action rows only',
                  trust='finite schema compiler, Python rule/model checkers; not proof-assistant verified')
    return result


def check(raw_input, raw_certificate) -> dict:
    p = presentation(raw_input)
    try:
        cert = snapshot(raw_certificate)
        result = _check(p, cert)
        need(encoded(cert['result']) == encoded(result), 'saved result is not evidence')
        return result
    except (ValueError, KeyError, TypeError, IndexError, RecursionError) as exc:
        raise InvalidCertificate(str(exc)) from exc


def explain(raw_input, raw_certificate, left: int, right: int, horizon: int = 2) -> dict:
    result = check(raw_input, raw_certificate)
    p, cert = presentation(raw_input), snapshot(raw_certificate)
    integer(horizon, 1, 2)
    n, nb = len(p['carrier']['names']), len(p['operators']['names'])
    integer(left, 0, n * (nb + 1) - 1)
    integer(right, 0, n * (nb + 1) - 1)
    level = cert['levels'][horizon - 1]
    labels = level['equality']['partition']
    equal = labels[left] == labels[right]
    return dict(schema='qkf-pure-row-query-v1', input_sha256=result['input_sha256'],
                left=left, right=right, horizon=horizon,
                relation='forced_equal' if equal else 'not_forced_equal',
                interpretation=('equality in the theory available at this horizon' if equal else
                                'one model separates these labels; not a universal disequality'),
                equality_evidence=level['equality'] if equal else None,
                separating_model=None if equal else level['model'],
                separate_values=None if equal else [labels[left], labels[right]],
                checked=True, lean_checked=False,
                scope='explanation after checking the complete input certificate; not a minimal proof')


def check_completion(raw_input, raw_witness) -> dict:
    """Verify a CHOSEN completion on a supplied quotient, not forced values."""
    p = presentation(raw_input)
    try:
        witness = snapshot(raw_witness)
        fields(witness, ('schema', 'input_sha256', 'carrier_partition', 'actions'))
        need(witness['schema'] == 'qkf-pure-row-completion-v1' and witness['input_sha256'] == digest(p),
             'completion witness binding')
        n, nb = len(p['carrier']['names']), len(p['operators']['names'])
        theta = partition(witness['carrier_partition'], n)
        qn, qops = quotient(n, p['carrier']['operations'], theta)
        actions = witness['actions']
        need(type(actions) is list and len(actions) == nb, 'completion action count')
        for action in actions:
            need(type(action) is list and len(action) == qn, 'completion action size')
            for x in action:
                integer(x, 0, qn - 1)
            for op in qops:
                for args in itertools.product(range(qn), repeat=op['arity']):
                    need(action[value(op['table'], args, qn)] == value(op['table'], [action[x] for x in args], qn),
                         'chosen action is not an endomorphism')
        for b, a, c in p['cells']:
            need(actions[b][theta[a]] == theta[c], 'chosen action violates supplied cell')
        return dict(status='completion_verified', claim='chosen_carrier_valued_completion_exists',
                    input_sha256=digest(p), carrier_partition=blocks(theta), actions=actions,
                    forced_values_checked=False, least_quotient_checked=False, lean_checked=False)
    except (ValueError, KeyError, TypeError, IndexError, RecursionError) as exc:
        raise InvalidCertificate(str(exc)) from exc
