"""Prepared original components and a common all-width resource envelope."""
import json,time
from qkf_certifier.kernel import digest,hashes,CONTRACT
from qkf_certifier.frontend import expression
from qkf_certifier.certificate import SCHEMA as PUBLIC_SCHEMA
from qkf_certifier.producer import normalize
from guard_kernel import produce as guards
from observer_kernel import produce as observers
from mask_observers import produce as masks
from regular_interfaces import order,target_for
from corpus_discovery import discover
from prefix_masks import shape,lower,allowed_node,supported
from prove_umin import one_bit,composition,LengthMachine,witness,WorkBudget
from corpus_branch_producer import produce as branches,ProofFailure
from word_oracle import evaluate
from corpus_io import load
from environment import save
import symbolic_producer,symbolic_bridge
import result_stage_kernel as native_kernel
import action_producer
import result_producer as observation_producer
import context_kernel
import producer_v5
from producer import Incomplete

BUDGETS=dict(states_total=100000,initial_enumeration_limit=100000,transition_attempts_total=2000000,max_branch_leaves=512,max_branch_depth=24,
             symbolic_search_nodes=10000,symbolic_fm_rows=100000,producer_seconds=60,replay_seconds=60)

class SharedSymbolicBudget:
 def __init__(self):self.nodes=0;self.rows=0
 def produce(self,expr):
  previous=producer_v5.old_produce
  def bounded(source,**kw):
   kw['node_cap']=min(kw['node_cap'],max(0,BUDGETS['symbolic_search_nodes']-self.nodes))
   kw['total_row_cap']=min(kw['total_row_cap'],max(0,BUDGETS['symbolic_fm_rows']-self.rows))
   try:
    cert,record=previous(source,**kw)
   except Incomplete as e:
    self.nodes+=e.record['stats']['search_nodes'];self.rows+=e.record['stats']['fm_constructed_rows'];raise
   self.nodes+=record['stats']['search_nodes'];self.rows+=record['stats']['fm_constructed_rows'];return cert,record
  producer_v5.old_produce=bounded
  try:return symbolic_producer.produce(expr)
  finally:producer_v5.old_produce=previous


def prepare(bundle,fs,entry,mode,budget):
 authority=context_kernel.source_authority(bundle,entry)
 initial=expression(fs,entry);nf,steps=normalize(initial)
 norm=dict(schema=PUBLIC_SCHEMA,sources=hashes(bundle),entry=entry,semantics=CONTRACT,initial_hash=digest(initial),steps=steps,normal_form=nf,target=None)
 g,gt=guards(nf,2);o,ot=observers(g,2)
 p,pt=(o,[]) if mode=='legacy' else masks(o,2)
 cur=p;action_rounds=[]
 for round_number in range(3):
  changed,trace,stats=action_producer.produce(cur,elementary_only=(mode=='arithmetic'))
  if not trace:break
  cleaned,cleanup=masks(changed,2)
  action_rounds.append(dict(trace=trace,after=changed,cleanup=cleanup,result=cleaned,stats=stats))
  cur=cleaned
 observation_rounds=[];observation_attempts=[]
 for round_number in range(3):
  selected,trace,stats=observation_producer.produce(cur,mode,authority)
  observation_attempts.append(stats)
  if not trace:break
  cleaned,cleanup=masks(selected,2)
  changed,action_trace,action_stats=action_producer.produce(cleaned)
  final_cleanup,action_cleanup=masks(changed,2)
  observation_rounds.append(dict(trace=trace,after=selected,cleanup=cleanup,cleaned=cleaned,
     action_trace=action_trace,action_after=changed,action_cleanup=action_cleanup,result=final_cleanup,
     stats=stats,action_stats=action_stats))
  cur=final_cleanup
 s,st,sr=budget.produce(cur)
 final,ft=masks(s,2)
 return dict(context_authority=authority,normalization=norm,guarded=g,guard_trace=gt,observed=o,observer_trace=ot,premasked=p,premask_trace=pt,
             action_rounds=action_rounds,observation_rounds=observation_rounds,observation_attempts=observation_attempts,symbolic_trace=st,postmask_trace=ft,final=final,final_hash=digest(final)),sr


def produce(name,mode,checkpoint):
 started=time.perf_counter();bundle,fs,raw=load(name);target,scope=target_for(name);sb=SharedSymbolicBudget()
 entries=[e for e in fs if e.startswith('partial_solution_') and not e.endswith(('_body','_cond'))] or ['solution']
 record=dict(case=name,mode=mode,target=target,target_scope=scope,status='running',sources=hashes(bundle),components={},symbolic_attempts={},
             totals=dict(states=0,search_states=0,transition_attempts=0),budgets=BUDGETS,component_count=len(entries))
 prepared={}
 for entry in entries:
  t=time.perf_counter();c,sr=prepare(bundle,fs,entry,mode,sb);prepared[entry]=c
  blockers=dict(__import__('collections').Counter(n[0] for n in order(lower(c['final'])) if not allowed_node(n)))
  record['components'][entry]=dict(status='prepared',blockers=blockers,native_lemmas=len(c['symbolic_trace']),action_rewrites=sum(len(x['trace']) for x in c['action_rounds']),observation_rewrites=sum(len(x['trace']) for x in c['observation_rounds']),prepare_seconds=time.perf_counter()-t)
  record['symbolic_attempts'][entry]=sr;record['symbolic_totals']=dict(search_nodes=sb.nodes,fm_constructed_rows=sb.rows)
  checkpoint(record,prepared)
 record['preparation_seconds']=time.perf_counter()-started
 if target is None:record['status']='unsupported_target';return None,record,prepared
 rows,bad=one_bit(fs,'solution',target,evaluate)
 if bad is not None:record.update(status='explicit_target_refuted',witness=bad);return None,record,prepared
 for entry in entries:
  c=prepared[entry];final=c['final'];r=record['components'][entry];t=time.perf_counter()
  remaining={**BUDGETS,'states_total':BUDGETS['states_total']-record['totals']['search_states'],
             'transition_attempts_total':BUDGETS['transition_attempts_total']-record['totals']['transition_attempts']}
  try:
   if mode=='legacy':
    if not supported(final):raise ProofFailure(dict(status='unsupported_candidate'))
    sh=shape(final,target)
    if sh['initial_states']>remaining['states_total']:raise ProofFailure(dict(status='initial_state_budget'))
    if sh['nonterminal_attempts_per_state']>remaining['transition_attempts_total']:raise ProofFailure(dict(status='transition_branching_budget'))
    m=LengthMachine(final,target,remaining['transition_attempts_total'])
    try:p=discover(m,remaining['states_total'])
    except WorkBudget:p=dict(status='transition_attempt_budget')
    finally:record['totals']['search_states']+=getattr(m,'search_states',0)
    record['totals']['transition_attempts']+=m.attempts
    if p['status']!='proved_sound':raise ProofFailure(dict(status=p['status'],proof=p))
    c['proof']=dict(backend='legacy',invariant=p['states']);record['totals']['states']+=p['state_count']
   else:
    def progress(totals,leaf):
     r['progress']=totals;r['last_leaf']=leaf;checkpoint(record,prepared)
    p,totals,leaves=branches(final,target,remaining,progress,split=True)
    c['proof']=dict(backend='composed',tree=p);r['leaves']=leaves
    for k in record['totals']:record['totals'][k]+=totals[k]
   r.update(status='proved_component',search_seconds=time.perf_counter()-t)
  except (ProofFailure,ValueError) as e:
   problem=e.record if isinstance(e,ProofFailure) else dict(status='unsupported_candidate',reason=str(e))
   r.update(problem);r['search_seconds']=time.perf_counter()-t;record.update(status=problem['status'],stopped_at=entry)
   # If discovery found a real component witness, check the ORIGINAL full SSA.
   p=problem.get('proof',{})
   if p.get('status')=='counterexample' and 'letters' in p:
    wit=witness(fs,'solution',target,p['letters'],evaluate);record.update(status='explicit_target_refuted',witness=wit)
   if 'totals' in problem:
    for k in record['totals']:record['totals'][k]+=problem['totals'][k]
   checkpoint(record,prepared);return None,record,prepared
  checkpoint(record,prepared)
 used=composition(fs,entries,expression) if entries!=['solution'] else entries
 cert=dict(schema=native_kernel.SCHEMA,case=name,target=target,target_scope=scope,semantics=CONTRACT,sources=hashes(bundle),
           minimum_rewrite_width=2,width_one=rows,components=prepared,composition=used)
 record['status']='certificate_produced'
 return cert,record,prepared
