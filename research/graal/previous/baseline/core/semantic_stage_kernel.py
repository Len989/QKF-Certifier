"""Whole original MLIR certificate replay. No search is imported here."""
import json
from environment import ROOT
from corpus_io import load
from qkf_certifier.frontend import parse_bundle,expression
from qkf_certifier.kernel import replay as public_replay,digest,hashes,CONTRACT
from regular_interfaces import tree,check_invariant,target_for
from guard_kernel import replay as guard_replay
from observer_kernel import replay as observer_replay
from mask_observers import replay as mask_replay
from prove_umin import one_bit,composition,LengthMachine
from branch_kernel import verify_tree
from word_oracle import evaluate
import symbolic_bridge,action_kernel
import semantic_choice_kernel as observation_kernel
SCHEMA='qkf-original-corpus-certificate-v10-semantic-observations'


def replay_prepared(bundle,entry,c):
 if c['normalization']['entry']!=entry:raise ValueError('normalization entry')
 nf=public_replay(bundle,entry,c['normalization'])
 g=tree(c['guarded']);guard_replay(nf,c['guard_trace'],g,2)
 o=tree(c['observed']);observer_replay(g,c['observer_trace'],o,2)
 p=tree(c['premasked']);mask_replay(o,c['premask_trace'],p,2)
 rounds=c['action_rounds']
 if not isinstance(rounds,list) or len(rounds)>3:raise ValueError('native action rounds')
 for r in rounds:
  changed=action_kernel.replay(p,r['trace'],r['after'])
  p=mask_replay(changed,r['cleanup'],tree(r['result']),2)
 rounds=c['observation_rounds']
 if not isinstance(rounds,list) or len(rounds)>3:raise ValueError('observation rounds')
 for r in rounds:
  changed,steps=observation_kernel.replay(p,r['trace'],r['after'])
  cleaned=mask_replay(changed,r['cleanup'],tree(r['cleaned']),2)
  changed=action_kernel.replay(cleaned,r['action_trace'],r['action_after'])
  p=mask_replay(changed,r['action_cleanup'],tree(r['result']),2)
 s=symbolic_bridge.replay(p,c['symbolic_trace'])
 final=tree(c['final']);mask_replay(s,c['postmask_trace'],final,2)
 if digest(final)!=c['final_hash']:raise ValueError('component final expression')
 return final


def verify(name,cert):
 bundle,fs,_=load(name);target,scope=target_for(name)
 if cert['schema']!=SCHEMA or cert['case']!=name or cert['target']!=target or cert['target_scope']!=scope:raise ValueError('whole target binding')
 if cert['semantics']!=CONTRACT or cert['sources']!=hashes(bundle) or cert['minimum_rewrite_width']!=2:raise ValueError('whole source semantics')
 expected=[entry for entry in fs if entry.startswith('partial_solution_') and not entry.endswith(('_body','_cond'))]
 if not expected:expected=['solution']
 if set(cert['components'])!=set(expected):raise ValueError('full original component coverage')
 rows,bad=one_bit(fs,'solution',target,evaluate)
 if bad is not None or json.loads(json.dumps(rows))!=cert['width_one']:raise ValueError('original width-one proof')
 counts=dict(states=0,transitions=0,components=len(expected),native_lemmas=0,native_symbolic_steps=0,rewrites=0,action_rewrites=0,action_tail_steps=0,observation_rewrites=0,observation_proof_steps=0)
 for entry,c in cert['components'].items():
  final=replay_prepared(bundle,entry,c);proof=c['proof']
  if proof['backend']=='legacy':
   count=len(proof['invariant']);checks=check_invariant(LengthMachine(final,target),proof['invariant'])
  elif proof['backend']=='composed':
   v=verify_tree(final,target,proof['tree']);count=v['states'];checks=v['transitions']
  else:raise ValueError('component backend')
  counts['states']+=count;counts['transitions']+=checks
  if counts['states']>100000:raise ValueError('whole aggregate states')
  counts['native_lemmas']+=len(c['symbolic_trace'])
  for r in c['observation_rounds']:
   counts['observation_rewrites']+=len(r['trace'])
   counts['observation_proof_steps']+=sum(observation_kernel.proof_steps(t['proof']) for t in r['trace'])
   counts['action_rewrites']+=len(r['action_trace'])
   counts['action_tail_steps']+=sum(len(t['proof'].get('tail_derivation',[])) for t in r['action_trace'])
   counts['rewrites']+=len(r['trace'])+len(r['cleanup'])+len(r['action_trace'])+len(r['action_cleanup'])
  for r in c['action_rounds']:
   counts['action_rewrites']+=len(r['trace'])
   counts['action_tail_steps']+=sum(len(t['proof'].get('tail_derivation',[])) for t in r['trace'])
   counts['rewrites']+=len(r['trace'])+len(r['cleanup'])
  counts['rewrites']+=len(c['normalization']['steps'])+sum(len(c[k]) for k in ['guard_trace','observer_trace','premask_trace','symbolic_trace','postmask_trace'])
  for t in c['symbolic_trace']:
   v=symbolic_bridge.verify_symbolic(t['obligation'],t['certificate']);counts['native_symbolic_steps']+=v.get('total_recorded_steps',v.get('proof_nodes',0))
 if expected!=['solution']:
  used=composition(fs,expected,expression)
  if used!=cert['composition']:raise ValueError('original meet composition')
 else:
  if cert['composition']!=['solution']:raise ValueError('direct solution')
 return dict(status='proved_original_whole_all_positive_widths',**counts)
