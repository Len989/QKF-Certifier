"""Run32 fixed development population; no selection based on engine outcomes."""
import hashlib
import json
from pathlib import Path

BASELINE = 'c8c7b4eeaf848d31c8c324a4316ffec8aac81cda'
BASELINE_TREE = '4838b8badbb3a56f8a7d2a197ce6c0d3d6b3a77d'
CURRENT = 'eb2e68023e272c51710a25cdfe0a0ff8dd5642ac'
CURRENT_TREE = '4c1dfe4047c7bc44ca45e0dc3e73b37517859dda'
MODES = ('frozen_v3', 'closure_cells', 'closure_rows')
REPEATS = 3
POWER = ['and', ['positive'], ['popcount_eq', 1]]
TRUE = ['or', ['negative'], ['nonnegative']]
FALSE = ['and', ['negative'], ['nonnegative']]
NEW_BUDGETS = dict(max_states=64, max_observations=63, max_pullbacks=4096,
                   max_classes=64, max_target_states=8192, max_witness_bits=4096)
OLD_BUDGETS = dict(max_features=128, max_target_states=8192)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        f.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')


def load(path):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            require(k not in result, 'duplicate JSON key')
            result[k] = v
        return result
    def invalid(s):
        raise ValueError('nonfinite JSON: ' + s)
    return json.loads(Path(path).read_text(), object_pairs_hook=unique, parse_constant=invalid)


def population(inputs, accepted):
    """Known PR31 cases + predetermined variants/stress; Run27 remains untouched."""
    # Import the *accepted* declarations, not a second rewritten example list.
    from research.signed_targets.experiment import cases as prior_cases
    entries = []
    for name, source, target, width, external, expected in prior_cases(inputs):
        entries.append(dict(id=name, source=source, target=target,
                            group='prior_pr31', expected_semantics=expected,
                            native_width=width, external_development=external))
    variants = (
        ('variant_reordered', 'return (x & (x - 1)) == 0 && x > 0;'),
        ('variant_lowbit', 'return x > 0 && (x & (~x + 1)) == x;'),
        ('variant_local', 'long y = x - 1; return x > 0 && (y & x) == 0;'),
        ('variant_renamed', 'long temporary = x & (x - 1); return temporary == 0 && x > 0;'),
    )
    def add(name, body, goal, group, semantics):
        source = 'class Demo { public static boolean f(long x) { ' + body + ' } }'
        target = {'schema':'qkf-target-v2', 'kind':'signed_boolean_predicate',
                  'source':{'entry':{'class':'Demo','method':'f'},'word_type':'long'}, 'goal':goal}
        entries.append(dict(id=name, source=source, target=target, group=group,
                            expected_semantics=semantics, native_width=64, external_development=False))
    for name, body in variants:
        add(name, body, POWER, 'equivalent_power', 'certified')
    for exponent in (4, 8, 30, 31):
        constant = str(1 << exponent) + 'L'
        add('delayed_' + str(exponent), 'return x == '+constant+';', FALSE,
            'constant_depth_stress', 'refuted')
        add('tautology_' + str(exponent), 'return x == '+constant+' || x != '+constant+';', TRUE,
            'redundant_carrier_stress', 'certified')
    add('unsupported_shift', 'return (x >> 1) > 0;', POWER, 'unsupported_control', 'unspecified')
    power_body = 'return x > 0 && (x & (x - 1)) == 0;'
    for name in ('observation_budget', 'product_budget'):
        add(name, power_body, POWER, 'shared_budget_control', 'certified')
    add('source_budget', power_body, POWER, 'new_route_budget_control', 'certified')
    add('witness_budget', 'return (x & (x - 1)) == 0;', POWER,
        'new_route_budget_control', 'refuted')
    for e in entries:
        old, new = dict(OLD_BUDGETS), dict(NEW_BUDGETS)
        if e['id'] == 'observation_budget': old['max_features']=0; new['max_observations']=0
        if e['id'] == 'product_budget': old['max_target_states']=1; new['max_target_states']=1
        if e['id'] == 'source_budget': new['max_states']=1
        if e['id'] == 'witness_budget': new['max_witness_bits']=0
        e['budgets'] = {m: (old if m=='frozen_v3' else new) for m in MODES}
        e['comparison'] = ('asymmetric_control' if e['group']=='new_route_budget_control'
                           else 'same_obligation_route_limits_disclosed')
        e['source_sha256']=sha(e['source'].encode()); e['target_sha256']=sha(canonical(e['target']))
    require(len(entries)==28 and len({e['id'] for e in entries})==28, 'fixed Run32 population')
    return entries


def register(inputs, output, accepted):
    output=Path(output); output.mkdir(parents=True, exist_ok=False)
    entries=population(inputs, accepted)
    for e in entries:
        d=output/e['id']; d.mkdir(); (d/'source.java').write_text(e['source'],encoding='utf-8')
        save(d/'target.json',e['target'])
    inventory=[{k:v for k,v in e.items() if k not in {'source','target'}} for e in entries]
    save(output/'CASES.json', {'schema':'qkf-run32-cases-v1','cases':inventory,
                             'count':len(entries),'new_holdout':False})
    return inventory
