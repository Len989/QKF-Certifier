"""Untrusted partitioning and BFS. The checker imports none of this module."""
from qkf_certifier.kernel import Z,TRUE,at,digest
from regular_interfaces import LETTERS
from corpus_discovery import discover
from prefix_masks import shape
from prove_umin import WorkBudget
from branch_kernel import (GuardMachine,consequence,specialize,first_select,guard)
from word_oracle import expr_value

class ProofFailure(Exception):
    def __init__(self,record):self.record=record;super().__init__(str(record))

def produce(initial,target,budgets,progress=None,split=True):
    totals={'states':0,'search_states':0,'transition_attempts':0,'leaves':0,'branches':0,'guard_refinements':0};leaves=[]
    def visit(path,depth):
        if consequence(path,TRUE)=='empty':
            totals['leaves']+=1;return {'kind':'propositionally_empty'}
        cur=specialize(initial,path);where=first_select(cur)
        if split and where is not None and depth<budgets['max_branch_depth']:
            p=at(cur,where)[1];totals['branches']+=1
            yes=visit(path+((p,True),),depth+1);no=visit(path+((p,False),),depth+1)
            return {'kind':'split','select_path':where,'predicate_hash':digest(p),'true':yes,'false':no}
        totals['leaves']+=1
        if totals['leaves']>budgets['max_branch_leaves']:raise ProofFailure({'status':'leaf_budget'})
        c={'expression_hash':digest(cur),'guard_hash':digest(guard(path))}
        row={'leaf':totals['leaves'],'depth':depth,'path':path,'expression_hash':digest(cur),'status':'top' if cur==('pair',Z,Z) else 'pending'}
        if cur==('pair',Z,Z):c['kind']='top';leaves.append(row);return c
        indices=[] if split else list(range(len(path)));attempts=[]
        while True:
            weaker=tuple(path[i] for i in indices)
            remaining=budgets['transition_attempts_total']-totals['transition_attempts']
            g=guard(weaker);wrapped=('pair',('select',g,cur[1],Z),('select',g,cur[2],Z))
            sh=shape(wrapped,target)
            if sh['initial_states']>budgets['initial_enumeration_limit']:raise ProofFailure(dict(status='initial_enumeration_budget',shape=sh))
            m=GuardMachine(cur,target,weaker,remaining)
            row.update(initial_states=len(m.initial),unrestricted_initial_states=m.unrestricted_initial_count)
            if len(m.initial)>budgets['states_total']-totals['search_states']:raise ProofFailure({'status':'initial_state_budget'})
            try:p=discover(m,budgets['states_total']-totals['search_states']) if m.initial else {'status':'proved_sound','states':[],'state_count':0}
            except WorkBudget:p={'status':'transition_attempt_budget'}
            finally:
                totals['transition_attempts']+=m.attempts;totals['search_states']+=getattr(m,'search_states',0)
            attempt={'assumption_indices':list(indices),'status':p['status'],'transition_attempts':m.attempts,'states':p.get('state_count',p.get('states_explored'))}
            attempts.append(attempt)
            if p['status']!='counterexample':break
            letters=[LETTERS[i] for i in p['letters']];w=len(letters)
            values=[sum(row[i]<<j for j,row in enumerate(letters)) for i in range(6)]
            violated=[i for i,(g,v) in enumerate(path) if bool(expr_value(g,values,w))!=v]
            attempt['witness']={'width':w,'input_masks':values[:4],'concrete_inputs':values[4:],'violated_path_literals':violated}
            if not violated:break  # A real leaf counterexample, not merely a too-weak guard.
            fresh=[i for i in violated if i not in indices]
            if not fresh:raise ProofFailure({'status':'guard_witness_inconsistent','attempt':attempt})
            indices=sorted(indices+[fresh[0]]);totals['guard_refinements']+=1
        row['guard_trials']=attempts;row['assumption_indices']=indices
        row.update(status=p['status'],transition_attempts=m.attempts,states=p.get('state_count',p.get('states_explored')));leaves.append(row)
        if progress:progress(dict(totals),row)
        if p['status']!='proved_sound':raise ProofFailure({'status':p['status'],'leaf_record':row,'proof':p,'totals':totals})
        totals['states']+=p['state_count'];c.update(kind='invariant',invariant=p['states'],assumption_indices=indices,proof_guard_hash=digest(guard(tuple(path[i] for i in indices))));return c
    try:certificate=visit((),0)
    except ProofFailure as e:
        e.record.setdefault('totals',dict(totals));e.record.setdefault('completed_leaves',leaves);raise
    except ValueError as e:
        raise ProofFailure(dict(status='unsupported_candidate',reason=str(e),totals=dict(totals),completed_leaves=leaves))
    return certificate,totals,leaves
