"""Bounded source-directed selection; all chosen facts are replayed by kernel."""
from qkf_certifier.kernel import at,replace,digest,children
import action_kernel as kernel


def produce(initial, elementary_only=False):
    root=initial;trace=[];attempts=0;tail_attempts=0
    def attempt(path):
        nonlocal root,attempts,tail_attempts
        old=at(root,path)
        choices=[('elementary',None)]
        if not elementary_only:choices.append(('dependent-count-action',None))
        if not elementary_only and old[0] in kernel.SHIFTS | kernel.MASKS:
            choices += [('width-action',t) for t in range(1,kernel.MAX_THRESHOLD+1)]
        for rule,parameter in choices:
            attempts+=1;tail_attempts+=rule=='width-action'
            try:after,proof=kernel.apply_rule(old,rule,parameter)
            except ValueError:continue
            if after==old:continue
            new=replace(root,path,after)
            trace.append(dict(schema=kernel.SCHEMA,path=path,rule=rule,parameter=parameter,
                              source_hash=digest(old),after=after,proof=proof,
                              before_hash=digest(root),after_hash=digest(new)))
            root=new
            if len(trace)>2000:raise RuntimeError('native action rewrite budget')
            return True
        return False
    def visit(path):
        while attempt(path):pass
        for i in children(at(root,path)):visit(path+[i])
        if attempt(path):visit(path)
    visit([])
    return root,trace,dict(rule_attempts=attempts,tail_attempts=tail_attempts,
                           rewrites=len(trace),infinite_tail_derivation_steps=sum(len(t['proof'].get('tail_derivation',[])) for t in trace))
