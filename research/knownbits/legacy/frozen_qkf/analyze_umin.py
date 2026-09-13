#!/usr/bin/env python3
"""Compare against the 70-certificate count-mask baseline and explain Umin."""
import argparse
import collections
import itertools
import json
import sys
from pathlib import Path
from audit_fixed import validate_freeze
from regular_interfaces import KB
ROOT=Path(__file__).resolve().parent


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--repo',type=Path,required=True)
    ap.add_argument('--results',type=Path,default=ROOT/'results');args=ap.parse_args()
    repo=args.repo.resolve();validate_freeze(repo);sys.path[:0]=[str(repo/'src'),str(repo/'tests')]
    from qkf_certifier.frontend import parse_bundle
    from word_oracle import evaluate
    base=json.loads((ROOT/'baseline/proofs.json').read_text());p=json.loads((args.results/'proofs.json').read_text())
    audit=json.loads((args.results/'observer_audit.json').read_text())
    key=lambda r:(r['operator'],r['entry'])
    old={key(r):r for r in base['records']};current={key(r):r for r in p['records']}
    before={k for k,r in old.items() if r['status']=='proved_sound'}
    after={k for k,r in current.items() if r['status']=='proved_sound'}
    assert before<=after
    old_bad={k for k,r in old.items() if 'witness' in r};now_bad={k for k,r in current.items() if 'witness' in r}
    assert old_bad<=now_bad
    assert all(current[k]['target_scope']=='stronger_unconditional_modular_target_flags_not_modeled' for k in now_bad)
    fresh=[]
    for k in sorted(after-before):
        r=current[k];op=r['operator'];source=(ROOT/'fixtures/corpus'/op/'solution.mlir').read_text();bundle={'program':source}
        if 'func.call @meet(' in source:bundle['meet']=(ROOT/'fixtures/helpers/meet.mlir').read_text()
        if 'func.call @getTop(' in source:bundle['top']=(ROOT/'fixtures/helpers/top.mlir').read_text()
        fs=parse_bundle(bundle);informative=0;example=None
        for rows in itertools.product(KB,repeat=6):
            vals=[sum(rows[2*j+i//2][i%2]<<j for j in range(3)) for i in range(4)]
            z,o=evaluate(fs,[tuple(vals[:2]),tuple(vals[2:])],3,r['entry'])
            if z or o:
                informative+=1
                if example is None:example={'width':3,'input_masks':vals,'output_masks':[z,o]}
        entry={a:r[a] for a in ('operator','entry','target','target_scope','states','valid_transition_checks','observer_rules','certificate')}
        entry.update(non_top_outputs_among_729_width_three_inputs=informative,non_top_example=example);fresh.append(entry)
    ordinary=[r for r in p['records'] if r['target_scope']=='explicit_total_target' and r['status']=='unsupported_candidate']
    usage={}
    for r in audit['records']:
        if r['role']!='component':continue
        for rule in r['observer_rules']:
            if rule.startswith('obs:'):usage.setdefault(rule,[]).append([r['operator'],r['entry']])
    umin=[r for r in p['records'] if r['operator']=='KnownBits_Umin']
    result={
        'previous_proof_count':len(before),'current_proof_count':len(after),'all_previous_proofs_preserved':True,
        'new_proofs':fresh,'new_proof_scopes':dict(collections.Counter(r['target_scope'] for r in fresh)),
        'new_counterexamples':[current[k] for k in sorted(now_bad-old_bad)],
        'retained_counterexample_count':len(old_bad),'current_counterexample_count':len(now_bad),
        'all_counterexamples_are_stronger_flag_obligations':True,
        'umin_components':[{k:r[k] for k in ('entry','status','states','valid_transition_checks','observer_rewrites','observer_rules')} for r in umin],
        'umin_whole':next(r for r in p['whole_records'] if r['operator']=='KnownBits_Umin'),
        'new_proof_state_sum':sum(r['states'] for r in fresh),
        'new_proof_transition_checks':sum(r['valid_transition_checks'] for r in fresh),
        'total_proof_state_sum':sum(current[k]['states'] for k in after),
        'total_proof_transition_checks':sum(current[k]['valid_transition_checks'] for k in after),
        'old_proof_state_reduction':sum(old[k]['states']-current[k]['states'] for k in before),
        'old_proof_transition_check_reduction':sum(old[k]['valid_transition_checks']-current[k]['valid_transition_checks'] for k in before),
        'old_proofs_with_changed_cost':[{ 'operator':k[0],'entry':k[1],'old_states':old[k]['states'],'new_states':current[k]['states']} for k in sorted(before) if old[k]['states']!=current[k]['states']],
        'budgets_exhausted':sum('budget' in r['status'] for r in p['records']),
        'observer_rule_component_usage':usage,
        'ordinary_unresolved_count':len(ordinary),
        'ordinary_blocker_presence':dict(collections.Counter(op for r in ordinary for op in r['blockers'])),
        'ordinary_residuals':[{k:r[k] for k in ('operator','entry','blockers','observer_rules')} for r in ordinary],
        'by_family':[{'operator':r['operator'],'components':r['component_count'],
                      'previous_proofs':sum(k[0]==r['operator'] for k in before),'current_proofs':r['proved_components'],
                      'whole_status':r['status']} for r in p['whole_records']],
        'scope':'Source-bound proof coverage; no SMT timing claim. New observer identities are mathematical lemmas implemented in a trusted Python kernel.',
    }
    (args.results/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('observer_rule_component_usage','ordinary_residuals','by_family')},indent=2))


if __name__=='__main__':main()
