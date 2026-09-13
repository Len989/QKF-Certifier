"""The inherited BFS, with attempted-state accounting even on interruption.

No transition, search order, acceptance condition or invariant checker changes.
"""
def discover(machine,max_states=20000):
 states=list(machine.initial);parents={s:None for s in states};edges=0
 machine.search_states=len(states)
 for state in states:
  for li,rg,(nxt,_,_) in machine.successors(state,True):
   edges+=1
   if nxt[-1]:
    letters=[li];p=state
    while parents[p] is not None:
     p,previous_letter=parents[p];letters.append(previous_letter)
    return dict(status='counterexample',states_explored=len(states),letters=list(reversed(letters)),transitions_examined=edges)
  for li,rg,(nxt,_,_) in machine.successors(state,False):
   edges+=1
   if nxt not in parents:
    if len(states)>=max_states:return dict(status='budget_exceeded',states_explored=len(states))
    parents[nxt]=state,li;states.append(nxt);machine.search_states=len(states)
 assert len(states)<=machine.bound
 return dict(status='proved_sound',states=states,state_count=len(states),transitions_examined=edges,state_bound=machine.bound)
