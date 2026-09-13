"""Untrusted count proposal and bounded lower-interface probe, shared budget."""
import time
import kernel
import bridge
import prefix
from producer import produce as old_produce,Incomplete
from kernel_saturation import produce as zero_ground
from nonzero_ground import produce as nonzero_ground

NODE_CAP=100000
ROW_CAP=500000
PROBE_NODES=8
PROBE_ROWS=1000
PREFIX_NODES=1024
PREFIX_ROWS=40000
ZERO_NODES=512
ZERO_ROWS=20000
FM_CALL_ROWS=20000


class Budget:
    def __init__(self,checkpoint):
        self.checkpoint=checkpoint
        self.record=dict(status='running',attempts=[],prefix_candidates=[],zero_candidates=[],
                         totals=dict(search_nodes=0,fm_constructed_rows=0),
                         budgets=dict(search_nodes=NODE_CAP,fm_constructed_rows=ROW_CAP,
                                      probe_nodes=PROBE_NODES,probe_rows=PROBE_ROWS,
                                      prefix_nodes=PREFIX_NODES,prefix_rows=PREFIX_ROWS,
                                      zero_nodes=ZERO_NODES,zero_rows=ZERO_ROWS,fm_call_rows=FM_CALL_ROWS))
    def search(self,source,role,index=None,node_limit=NODE_CAP,row_limit=ROW_CAP,max_level=2):
        seen=set();used_nodes=used_rows=0;last='no_attempt'
        for level in range(max_level+1):
            try:signature=tuple(c['formula_hash'] for c in kernel.compile_source(source,level))
            except kernel.Unsupported as error:
                self.record['attempts'].append(dict(role=role,candidate=index,level=level,status='unsupported',reason=str(error)))
                return None,'unsupported'
            if signature in seen:
                self.record['attempts'].append(dict(role=role,candidate=index,level=level,status='same_interface_skipped'));continue
            seen.add(signature)
            nodes=min(node_limit-used_nodes,NODE_CAP-self.record['totals']['search_nodes'])
            rows=min(row_limit-used_rows,ROW_CAP-self.record['totals']['fm_constructed_rows'])
            if min(nodes,rows)<=0:return None,'cumulative_resource_budget'
            cert=None
            try:cert,attempt=old_produce(source,node_cap=nodes,total_row_cap=rows,fm_cap=FM_CALL_ROWS,interface_level=level)
            except Incomplete as error:attempt=error.record
            attempt.update(role=role,candidate=index,level=level);self.record['attempts'].append(attempt)
            for key in self.record['totals']:self.record['totals'][key]+=attempt['stats'][key]
            used_nodes+=attempt['stats']['search_nodes'];used_rows+=attempt['stats']['fm_constructed_rows']
            self.checkpoint(self.record);last=attempt['status']
            if cert is not None:return cert,last
            if last!='unknown_abstract_feasible':break
        return None,last


def old_tail(source,budget):
    """The v4 plan, using the SAME cumulative budget as prefix work."""
    planned,_=bridge.candidates(source);accepted=[];entries=[];ground=None
    for i,candidate in enumerate(planned):
        cert,status=budget.search(bridge.bridge_source(source,candidate),'zero_bridge',i,ZERO_NODES,ZERO_ROWS)
        budget.record['zero_candidates'].append(dict(candidate_hash=candidate['candidate_hash'],status=status))
        if cert is not None:
            if ground is None:ground=zero_ground(bridge.ground_source())
            accepted.append(candidate)
            entries.append(dict(candidate_hash=candidate['candidate_hash'],candidate=candidate,bridge_certificate=cert))
    transformed,steps=bridge.residual(source,accepted)
    final,status=budget.search(transformed,'residual')
    if final is None:
        budget.record['partial_zero_certificate']=dict(lemmas=entries,ground_certificate=ground,
                                                       residual_hash=kernel.digest(transformed),rewrite_trace=steps)
        return None,None,status
    if not planned:return 'v3',final,status
    cert=dict(schema=bridge.SCHEMA,source_hash=kernel.digest(source),lemmas=entries,ground_certificate=ground,
              residual_hash=kernel.digest(transformed),rewrite_trace=steps,residual_certificate=final)
    return 'v4',cert,status


def produce(source,checkpoint=lambda record:None):
    start=time.perf_counter();budget=Budget(checkpoint);record=budget.record
    planned,omitted=prefix.candidates(source);record.update(planned_prefix_candidates=len(planned),omitted_prefix_candidates=omitted)
    lemmas=[];ground=None;tail=None;backend=None
    if planned:
        tail,status=budget.search(source,'lower_interface_probe',node_limit=PROBE_NODES,row_limit=PROBE_ROWS,max_level=0)
        record['probe_status']=status
        if tail is not None:backend='v3'
    if tail is None:
        for i,candidate in enumerate(planned):
            d=candidate['descriptor'];number=['min','w',['add',[d['kind'],d['argument']],d['amount']]]
            try:problem=prefix.bridge_source(source,candidate,number)
            except ValueError as error:
                record['prefix_candidates'].append(dict(candidate_hash=candidate['candidate_hash'],status='proposal_syntax_unsupported',reason=str(error)));continue
            cert,status=budget.search(problem,'prefix_bridge',i,PREFIX_NODES,PREFIX_ROWS)
            record['prefix_candidates'].append(dict(candidate_hash=candidate['candidate_hash'],status=status))
            if cert is not None:
                if ground is None:ground=nonzero_ground(prefix.ground_source())
                spec=prefix.specification(source,candidate,number)
                lemmas.append(dict(candidate_hash=candidate['candidate_hash'],candidate=candidate,number=number,
                                   native_map_hash=kernel.digest(spec),native_rules=spec['native_rules'],bridge_certificate=cert))
        transformed,trace=prefix.residual(source,lemmas)
        backend,tail,status=old_tail(transformed,budget)
    else:transformed,trace=prefix.residual(source,[])
    record.update(status=status,accepted_prefix_lemmas=len(lemmas),prefix_rewrite_steps=len(trace),
                  producer_seconds=time.perf_counter()-start)
    if tail is None:
        record['partial_prefix_certificate']=dict(lemmas=lemmas,ground_certificate=ground,
                                                  residual_hash=kernel.digest(transformed),rewrite_trace=trace)
        raise Incomplete(record)
    cert=dict(schema=prefix.SCHEMA,source_hash=kernel.digest(source),lemmas=lemmas,ground_certificate=ground,
              residual_hash=kernel.digest(transformed),rewrite_trace=trace,tail_backend=backend,tail=tail)
    return cert,record
