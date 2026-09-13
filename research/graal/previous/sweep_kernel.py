"""Check a finite closed observation carrier: induction covers every word length."""
from row_kernel import compare, require, replay_rows

SCHEMA='qkf-universal-upper-sweep-v1'
START=(7,0,0,0,0)
ALPHABET=[(a,o,u,x,y) for a,o in [(0,0),(0,1),(1,0)] for u in (0,1)
          for x in range(a,a+o+1) for y in range(a,a+o+1)]


def prepend(a,b,suffix):
    return compare(a,b) or suffix


def transition(state,column,rows):
    allowed,base_bound,x_bound,y_bound,x_y=state
    a,optional,u,x,y=column
    new_allowed=rows[(a,optional,u,y,base_bound)][allowed]
    return (new_allowed,prepend(a,u,base_bound),prepend(x,u,x_bound),
            prepend(y,u,y_bound),prepend(x,y,x_y))


def boundary(state,sign,bound_sign):
    allowed,base_bound,x_bound,y_bound,x_y=state
    h=compare(1-sign,1-bound_sign)
    source_valid=bool(allowed & (1<<(h+1)))
    candidate_feasible=prepend(1-sign,1-bound_sign,x_bound)<=0
    output_feasible=prepend(1-sign,1-bound_sign,y_bound)<=0
    maximal=x_y<=0
    return dict(source_valid=source_valid,candidate_feasible=candidate_feasible,
                output_feasible=output_feasible,candidate_below_output=maximal,
                bad=source_valid and candidate_feasible and not(output_feasible and maximal))


def replay(guard,certificate):
    c=certificate
    require(set(c)=={'schema','guard','rows','states','initial','edges','boundaries','conclusion'}, 'sweep fields')
    require(c['schema']==SCHEMA and c['guard']==guard, 'source sweep guard binding')
    rows=replay_rows(guard,c['rows'])
    states=[tuple(q) for q in c['states']]
    require(states and len(states)<=648 and len(set(states))==len(states), 'finite observation carrier')
    for q in states:
        require(len(q)==5 and type(q[0]) is int and 0<=q[0]<8 and all(type(x) is int and x in (-1,0,1) for x in q[1:]), 'observation state')
    require(type(c['initial']) is int and 0<=c['initial']<len(states) and states[c['initial']]==START, 'empty suffix')
    require(len(c['edges'])==len(states) and len(c['boundaries'])==len(states), 'complete induction obligations')
    for i,q in enumerate(states):
        require(len(c['edges'][i])==len(ALPHABET), 'all bit columns')
        for col,j in zip(ALPHABET,c['edges'][i]):
            require(type(j) is int and 0<=j<len(states) and states[j]==transition(q,col,rows), 'closed observation transition')
        expected=[boundary(q,a,u) for a in (0,1) for u in (0,1)]
        require(c['boundaries'][i]==expected and not any(r['bad'] for r in expected), 'signed final property')
    conclusion=dict(widths='all positive',inputs='all fixed-sign mask cylinders and all signed bounds',
                    theorem='For every x in the cylinder with x <= bound, the source output y is in the cylinder, y <= bound, and x <= y.',
                    induction='Empty suffix, every nonsign column, then exactly one sign column')
    require(c['conclusion']==conclusion, 'sweep theorem')
    return dict(status='proved_all_widths_all_inputs',states=len(states),columns=len(ALPHABET),
                transitions=len(states)*len(ALPHABET),sign_boundaries=4*len(states),
                native_row_templates=len(rows),protected_carrier_size=8,
                forced_row_domain=8,central_carrier_quotient='diagonal',
                row_kernel_class_counts=sorted({len(c['kernel']) for c in c['rows']}))
