"""Export checked run-2 factors/goals to a separate, data-only Lean pilot.

Python acceptance here establishes source/package identity and finite replay;
it NEVER claims that a Lean compiler has accepted the generated proof terms.
No producer search, old phase model, JVM or solver is imported.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .ascending_kernel import ALPHABET, Runner
from .model import digest, integer, require
from .run_io import read_json
from .run_package import check_package
from .target_kernel import System
from .target_rules import advance, columns, compile_spec, initial, violation

SCHEMA = 'qkf-lean-target-export-v1'
CASES = ('original', 'irrelevant_register')
ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'research/observations/evidence/typed_targets'


def successor_goal():
    """Caller-owned fixed goal, independent of any package or its compiled program."""
    return {'schema': 'qkf-word-observation-spec-v1', 'profile': 'ascending',
            'domain': 'legal-masked-entry-v1', 'quantifier': 'forall_legal_alternative',
            'preconditions': [], 'obligations': [
                ['subset', 'must', 'output'], ['subset', 'output', 'may'],
                ['implies', ['ne', 'seed', 'may'], ['ult', 'seed', 'output']],
                ['implies', ['ult', 'seed', 'alternative'], ['ule', 'output', 'alternative']],
                ['implies', ['eq', 'seed', 'may'], ['eq', 'output', 'must']]]}


def inputs(name):
    require(name in CASES, 'fixed run-4 evidence case')
    directory = EVIDENCE / f'ascending.{name}.cyclic_successor'
    source = (directory / 'source.java').read_bytes().decode('utf-8')
    goal = successor_goal()
    require(digest(read_json(directory / 'goal.json')) == digest(goal), 'external successor goal')
    package = read_json(directory / 'package.json', package=True)
    return source, goal, package


def build_export(source, goal, package):
    require(digest(goal) == digest(successor_goal()), 'run-4 numerical route fixes the external successor goal')
    result = check_package(source, goal, package)
    require(result['status'] == 'certified', 'only a replayed positive target proof can be exported')
    source_cert, proof = (package['proofs'][k] for k in ('source', 'property'))
    require(proof['kind'] == 'closed_observation', 'finite positive target carrier required')
    system = System(source, source_cert, goal)
    runner = Runner(source, source_cert)
    states = [r['state'] for r in proof['states']]
    ids = {tuple(s): i for i, s in enumerate(states)}
    require(len(ids) == len(states), 'distinct exported states')
    transitions = [[ids[system.advance(tuple(s), c)] for c in system.alphabet] for s in states]
    cells = [[{'output': runner.cells[q, a][0] == '1', 'next': runner.cells[q, a][1]}
              for a in ALPHABET] for q in range(system.classes)]
    exported = {'schema': SCHEMA, 'toolchain': 'leanprover/lean4:v4.33.0',
                'binding': {'source_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(),
                            'goal_sha256': digest(goal), 'package_sha256': digest(package),
                            'source_certificate_sha256': digest(source_cert)},
                'program': deepcopy(system.program),
                'alphabet': list(system.alphabet), 'source_alphabet': list(ALPHABET),
                'machine': {'initial': runner.initial, 'cells': cells},
                'states': deepcopy(states), 'edges': transitions, 'initial': 0,
                'claim': 'candidate Lean proof for an explicitly supplied source factor',
                'lean_checked': False}
    validate_finite(exported)
    return exported


def validate_finite(data):
    """Independent table replay, including output-independent rival projection.

    This checks the exported representation, not Lean elaboration or the kernel.
    Source identity still requires check_export with the external inputs.
    """
    require(type(data) is dict and set(data) == {
        'schema', 'toolchain', 'binding', 'program', 'alphabet', 'source_alphabet',
        'machine', 'states', 'edges', 'initial', 'claim', 'lean_checked'}, 'export fields')
    require(data['schema'] == SCHEMA and data['toolchain'] == 'leanprover/lean4:v4.33.0', 'export version')
    require(data['lean_checked'] is False, 'Python export cannot claim Lean acceptance')
    require(type(data['binding']) is dict and set(data['binding']) == {
        'source_sha256', 'goal_sha256', 'package_sha256', 'source_certificate_sha256'}, 'binding fields')
    require(all(type(v) is str and len(v) == 64 and all(c in '0123456789abcdef' for c in v)
                for v in data['binding'].values()), 'binding digests')
    expected = compile_spec(successor_goal())
    require(digest(data['program']) == digest(expected), 'protected target program')
    require(data['alphabet'] == list(columns('ascending')) and data['source_alphabet'] == list(ALPHABET),
            'complete fixed alphabets')
    machine = data['machine']
    require(type(machine) is dict and set(machine) == {'initial', 'cells'}, 'machine fields')
    cells = machine['cells']
    require(type(cells) is list and 1 <= len(cells) <= 64, 'finite source carrier')
    require(integer(machine['initial'], 0, len(cells) - 1), 'source initial class')
    for row in cells:
        require(type(row) is list and len(row) == 4, 'one cell per source input')
        for c in row:
            require(type(c) is dict and set(c) == {'output', 'next'}
                    and type(c['output']) is bool and integer(c['next'], 0, len(cells) - 1), 'typed source cell')
    states, edges = data['states'], data['edges']
    require(type(states) is list and 1 <= len(states) <= 8192 and type(edges) is list
            and len(states) == len(edges) and data['initial'] == 0 and type(data['initial']) is int,
            'finite target carrier and edges')
    from .target_rules import valid_state
    for s in states:
        require(type(s) is list and len(s) == len(expected['atoms']) + 2
                and integer(s[0], 0, len(cells) - 1) and type(s[1]) is bool
                and valid_state(expected, s[2:]), 'typed exported joint state')
        require(not s[1] or violation(expected, s[2:]) is None, 'exported protected target obligation')
    require(len(set(map(tuple, states))) == len(states), 'distinct exported joint states')
    require(states[0] == [machine['initial'], False, *initial(expected)], 'actual empty start')
    for s, row in zip(states, edges):
        require(type(row) is list and len(row) == 6, 'complete target row')
        for symbol, nxt in zip(data['alphabet'], row):
            require(integer(nxt, 0, len(states) - 1), 'target edge range')
            cell = cells[s[0]][ALPHABET.index(symbol[:3])]
            env = dict(zip(('must', 'may', 'seed', 'alternative'), map(int, symbol)))
            env['output'] = int(cell['output'])
            actual = [cell['next'], True, *advance(expected, s[2:], env)]
            require(actual == states[nxt], 'recomputed exported transition')
    return {'status': 'finite_export_checked', 'source_classes': len(cells),
            'states': len(states), 'transitions': len(states) * 6, 'lean_checked': False}


def check_export(source, goal, package, exported):
    require(digest(exported) == digest(build_export(source, goal, package)),
            'export must correspond to the supplied source, goal and complete proof')
    return validate_finite(exported)


def _bool(value):
    require(type(value) is bool, 'Lean Boolean literal')
    return 'true' if value else 'false'


def _word(expr):
    if type(expr) is str:
        if expr in ('zero', 'ones'): return '.' + expr
        require(expr in ('must', 'may', 'seed', 'output', 'alternative'), 'Lean word variable')
        return '(.var .' + expr + ')'
    op = {'bit_not': 'bnot', 'bit_and': 'band', 'bit_or': 'bor', 'bit_xor': 'bxor'}[expr[0]]
    return '(.' + op + ' ' + ' '.join(_word(e) for e in expr[1:]) + ')'


def _formula(expr):
    if type(expr) is bool: return '(.literal ' + _bool(expr) + ')'
    op = expr[0]
    if op in ('query', 'ult', 'ule'):
        require(integer(expr[1], 0, 15), 'Lean formula index')
        return '(.' + {'query': 'query', 'ult': 'lt', 'ule': 'le'}[op] + ' ' + str(expr[1]) + ')'
    if op == 'not': return '(.neg ' + _formula(expr[1]) + ')'
    if op == 'implies': return '(.implies ' + _formula(expr[1]) + ' ' + _formula(expr[2]) + ')'
    require(op in ('and', 'or'), 'Lean connective')
    name = 'conj' if op == 'and' else 'disj'
    def fold(xs):
        if len(xs) == 1: return _formula(xs[0])
        return '(.' + name + ' ' + _formula(xs[0]) + ' ' + fold(xs[1:]) + ')'
    return fold(expr[1:])


def _conjunction(exprs):
    return _formula(['and', *exprs]) if len(exprs) > 1 else _formula(exprs[0]) if exprs else '(.literal true)'


def render_case(label, data):
    require(label in ('Original', 'Irrelevant'), 'fixed Lean namespace')
    validate_finite(data)
    p = data['program']; n = len(data['machine']['cells']); k = len(data['states'])
    lines = ['namespace ' + label, '', 'def program : Program :=', '  { atoms := [']
    for i, a in enumerate(p['atoms']):
        lines.append('      ⟨.' + a['kind'] + ', ' + _word(a['left']) + ', ' + _word(a['right'])
                     + '⟩' + (',' if i < len(p['atoms']) - 1 else '],'))
    lines += ['    premise := ' + _conjunction(p['preconditions']) + ',',
              '    target := ' + _conjunction(p['obligations']) + ' }', '',
              'theorem program_matches : program = successorProgram := by decide', '',
              f'def machine : Machine {n} :=', f"  {{ initial := {data['machine']['initial']}, cell := fun s a =>",
              '      match s.val, a.val with']
    for q, row in enumerate(data['machine']['cells']):
        for a, cell in enumerate(row): lines.append(f"      | {q}, {a} => ({_bool(cell['output'])}, {cell['next']})")
    lines += ['      | _, _ => (false, 0) }', '', f'def states (i : Fin {k}) : Observation {n} :=',
              '  match i.val with']
    for i, s in enumerate(data['states']):
        vals = [('(.order .' + {-1: 'lt', 0: 'eq', 1: 'gt'}[v] + ')') if a['kind'] == 'order'
                else '(.flag ' + _bool(v) + ')' for a, v in zip(p['atoms'], s[2:])]
        lit = f'⟨{s[0]}, {_bool(s[1])}, [' + ', '.join(vals) + ']⟩'
        lines.append('  | ' + (str(i) if i != k - 1 else '_') + ' => ' + lit)
    lines += ['', f'def edges (i : Fin {k}) (c : Column) : Fin {k} :=', '  match i.val, c.val with']
    for i, row in enumerate(data['edges']):
        for c, nxt in enumerate(row): lines.append(f'  | {i}, {c} => {nxt}')
    lines += ['  | _, _ => 0', '', f'def certificate : Certificate {n} {k} :=',
              '  ⟨states, edges, 0⟩', '',
              'theorem accepted : Accepted machine program certificate := by decide', '',
              'theorem formula_all_lengths (xs : List Column) :',
              '    good program (run (step machine program) (start machine program) xs) = true :=',
              '  closed_certificate_sound machine program certificate accepted xs', '',
              'theorem numerical_all_widths (xs : List Column) (positive : 0 < xs.length) :',
              '    SuccessorNumeric (run (concreteStep machine) (concreteStart machine) xs).numbers := by',
              '  apply cyclic_successor_all_widths machine certificate',
              '  · simpa only [program_matches] using accepted',
              '  · exact positive', '', 'end ' + label, '']
    return '\n'.join(lines)


def render_all(exports):
    require(set(exports) == set(CASES), 'both source-derived positive examples')
    return ('import QKFTarget.Numeric\n\n/- Generated from checked run-2 packages; no search or phases. -/\n'
            'set_option maxRecDepth 8192\nset_option maxHeartbeats 8000000\nnamespace QKFTarget\n\n'
            + render_case('Original', exports['original']) + '\n'
            + render_case('Irrelevant', exports['irrelevant_register']) + '\nend QKFTarget\n')


def export_all(directory, *, check_existing=False):
    directory = Path(directory)
    exports = {name: build_export(*inputs(name)) for name in CASES}
    rendered = render_all(exports)
    outputs = {name + '.json': (json.dumps(value, sort_keys=True, indent=2) + '\n').encode('utf-8')
               for name, value in exports.items()}
    outputs['Exported.lean'] = rendered.encode('utf-8')
    manifest = {name: hashlib.sha256(raw).hexdigest() for name, raw in outputs.items()}
    outputs['MANIFEST.json'] = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode('utf-8')
    if check_existing:
        require(directory.is_dir(), 'retained Lean export directory')
        require({p.name for p in directory.iterdir()} == set(outputs), 'retained Lean export population')
        for name, raw in outputs.items(): require((directory / name).read_bytes() == raw, 'retained Lean export: ' + name)
    else:
        directory.mkdir(parents=True, exist_ok=False)
        for name, raw in outputs.items(): (directory / name).write_bytes(raw)
    return {'status': 'export_replayed' if check_existing else 'exported',
            'cases': {name: validate_finite(value) for name, value in exports.items()}, 'lean_checked': False}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(json.dumps(export_all(args.output, check_existing=args.check), sort_keys=True))
