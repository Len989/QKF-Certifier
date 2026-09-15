"""Check ten negative Lean controls after building QKF.Targets.Checked.

For every case Lean first PROVES that its Boolean acceptance gate is false.
A separate process must then reject the claim that the same gate is true.
This distinguishes semantic rejection from accidental syntax/import failures.
No tracked Lean source is modified and no proof search dependency is installed.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

LEAN_ROOT = Path(__file__).resolve().parents[1]
PREFIX = '''import QKF.Targets.Checked
set_option maxRecDepth 16384
set_option maxHeartbeats 4000000
open QKF.Targets
open QKF.Targets.Data
'''
CASES = {
    'source_initial': '''
def badMachine : Machine 2 := { originalMachine with initial := 1 }
def gate : Bool := checkCertificate badMachine successorProgram originalCertificate
''',
    'certificate_initial': '''
def badCertificate : Certificate 7 2 9 := { originalCertificate with initial := 1 }
def gate : Bool := checkCertificate originalMachine successorProgram badCertificate
''',
    'edge': '''
def badCertificate : Certificate 7 2 9 := { originalCertificate with edges := fun _ _ => 0 }
def gate : Bool := checkCertificate originalMachine successorProgram badCertificate
''',
    'observed_mask_answer': '''
def badCertificate : Certificate 7 2 9 := { originalCertificate with
  states := fun i => if i.val == 2 then
    { (originalCertificate.states i) with answers := fun j =>
        if j.val == 0 then .boolean false else (originalCertificate.states i).answers j }
    else originalCertificate.states i }
def gate : Bool := checkCertificate originalMachine successorProgram badCertificate
''',
    'source_output_cell': '''
def badMachine : Machine 2 := { originalMachine with
  step := fun s i => if s.val == 0 && i.val == 1 then (false, 1) else originalMachine.step s i }
def gate : Bool := checkCertificate badMachine successorProgram originalCertificate
''',
    'positive_width_erasure': '''
def badCertificate : Certificate 7 2 9 := { originalCertificate with
  states := fun i => { (originalCertificate.states i) with nonempty := false } }
def gate : Bool := checkCertificate originalMachine successorProgram badCertificate
''',
    'typed_query': '''
def badProgram : Program 7 := { successorProgram with obligation := .query 3 }
def gate : Bool := checkCertificate originalMachine badProgram originalCertificate
''',
    'weak_goal_promotion': '''
def weakProgram : Program 7 := { successorProgram with obligation := .query 0 }
example : checkCertificate originalMachine weakProgram originalCertificate = true := by decide
def gate : Bool := decide (weakProgram.obligation = successorProgram.obligation)
''',
    'missing_independent_column': '''
def incomplete : Fin 5 → Column := fun j => ([0, 1, 3, 4, 5] : List Column).getD j.val 0
def gate : Bool := decide (∀ (i : Input) (b : Bool),
  allowed (must i) (may i) b = true →
    ∃ j : Fin 5, input (incomplete j) = i ∧ alternative (incomplete j) = b)
''',
    'low_bit_priority': '''
def gate : Bool := decide (compare (0 + digit true * 2) (1 + digit false * 2) = compare 0 1)
''',
}


def execute(path):
    return subprocess.run(['lake', 'env', 'lean', str(path)], cwd=LEAN_ROOT,
                          text=True, capture_output=True, timeout=90)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if shutil.which('lake') is None:
        raise SystemExit('lake is required; no negative Lean tests were executed')
    out.mkdir(parents=True, exist_ok=False)
    version = subprocess.run(['lake', 'env', 'lean', '--version'], cwd=LEAN_ROOT,
                             text=True, capture_output=True, check=True, timeout=90).stdout.strip()
    results = {}
    with tempfile.TemporaryDirectory(prefix='qkf-target-controls-') as temporary:
        root = Path(temporary)
        baseline = root / 'Positive.lean'
        baseline.write_text(PREFIX + 'example : checkCertificate originalMachine successorProgram originalCertificate = true := by decide\n', encoding='utf-8')
        good = execute(baseline)
        (out / 'positive.log').write_text(good.stdout + good.stderr, encoding='utf-8')
        if good.returncode:
            raise SystemExit('positive control failed; negative outcomes are not meaningful')
        for name, body in CASES.items():
            probe = root / 'Probe.lean'
            failure = root / 'FalseAcceptance.lean'
            probe_text = PREFIX + body + '\nexample : gate = false := by decide\n'
            false_text = PREFIX + body + '\nexample : gate = true := by decide\n'
            probe.write_text(probe_text, encoding='utf-8')
            failure.write_text(false_text, encoding='utf-8')
            rejected_gate = execute(probe)
            attempted_acceptance = execute(failure)
            (out / (name + '.probe.lean')).write_text(probe_text, encoding='utf-8')
            (out / (name + '.false_acceptance.lean')).write_text(false_text, encoding='utf-8')
            (out / (name + '.probe.log')).write_text(rejected_gate.stdout + rejected_gate.stderr, encoding='utf-8')
            text = attempted_acceptance.stdout + attempted_acceptance.stderr
            (out / (name + '.rejection.log')).write_text(text, encoding='utf-8')
            passed = rejected_gate.returncode == 0 and attempted_acceptance.returncode != 0
            results[name] = {'gate_false_proved': rejected_gate.returncode == 0,
                             'false_acceptance_rejected': attempted_acceptance.returncode != 0,
                             'passed': passed}
            if not passed:
                print(rejected_gate.stdout + rejected_gate.stderr + text)
                raise SystemExit('negative control did not reach its semantic gate: ' + name)
    summary = {'schema': 'qkf-lean-target-negative-v1', 'lean': version,
               'positive_control': 'passed', 'negative_controls': len(results), 'cases': results}
    (out / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, sort_keys=True))


if __name__ == '__main__':
    main()
