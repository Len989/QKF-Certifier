"""Untrusted Boolean case search and exact linear-refutation production."""
import collections,time
from kernel import SCHEMA,SEMANTICS,digest,compile_source,propagate,linear_rows
from linear_search import refute

class Incomplete(Exception):
    def __init__(self,record):self.record=record;super().__init__(repr(record))

def produce(source,node_cap=100000,fm_cap=20000,total_row_cap=500000,interface_level=0):
    started=time.perf_counter();compiled=compile_source(source,interface_level)
    stats={'search_nodes':0,'fm_calls':0,'fm_constructed_rows':0,'splits':0,'boolean_leaves':0,'linear_leaves':0,'max_depth':0}
    certificates=[];features=[]
    for ci,obligation in enumerate(compiled):
        cnf=obligation['cnf'];features.append({'claim':ci,'cnf_variables':cnf.next_id-1,'clauses':len(cnf.clauses),
            'count_parameters':len(obligation['counts']),'queried_bits':obligation['queried_bits'],'added_observations':obligation['added_observations']})
        def search(assignment,depth):
            if stats['search_nodes']>=node_cap:raise Incomplete({'status':'search_node_budget','claim':ci})
            stats['search_nodes']+=1;stats['max_depth']=max(stats['max_depth'],depth)
            assignment,clauses,conflict=propagate(cnf,assignment)
            if conflict:stats['boolean_leaves']+=1;return {'kind':'boolean'}
            rows,_=linear_rows(cnf,assignment)
            remaining=total_row_cap-stats['fm_constructed_rows']
            if remaining<=0:raise Incomplete({'status':'linear_work_budget','claim':ci})
            result=refute(rows,max_rows=min(fm_cap,remaining));stats['fm_calls']+=1
            work=result['stats'].get('constructed_rows',0);stats['fm_constructed_rows']+=work
            if result['status']=='unsat':stats['linear_leaves']+=1;return {'kind':'linear','weights':result['weights']}
            if result.get('reason')=='row_limit':raise Incomplete({'status':'linear_call_budget','claim':ci,'linear_result':result})
            if not clauses:raise Incomplete({'status':'unknown_abstract_feasible','claim':ci,'assignment':sorted(assignment.items()),'linear_result':result})
            # Literal occurrence in the shortest clauses; genuine exhaustive
            # split. Arithmetic infeasibility is tried at every node.
            size=min(map(len,clauses));short=[c for c in clauses if len(c)==size]
            frequency=collections.Counter(abs(l) for c in short for l in c)
            v=max(frequency,key=lambda k:(frequency[k],int(k in cnf.atoms),-k))
            stats['splits']+=1
            yes=dict(assignment);yes[v]=True;no=dict(assignment);no[v]=False
            return {'kind':'split','variable':v,'true':search(yes,depth+1),'false':search(no,depth+1)}
        try:proof=search({},0)
        except Incomplete as err:
            err.record.update(stats=stats,features=features,producer_seconds=time.perf_counter()-started)
            raise
        certificates.append({'formula_hash':obligation['formula_hash'],'tree':proof})
    cert={'schema':SCHEMA,'semantics':SEMANTICS,'source_hash':digest(source),'interface_level':interface_level,'proofs':certificates}
    return cert,{'status':'certificate_produced','stats':stats,'features':features,'producer_seconds':time.perf_counter()-started}
