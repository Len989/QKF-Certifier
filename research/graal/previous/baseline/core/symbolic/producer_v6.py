"""Untrusted representative selection, with all trials on one shared budget."""
import time
import kernel,bridge,prefix,reconstruction
from producer import Incomplete
from producer_v5 import (Budget,produce as v5_produce,old_tail,nonzero_ground,
                        PROBE_NODES,PROBE_ROWS,PREFIX_NODES,PREFIX_ROWS)

INSTANCE_NODES=1024
INSTANCE_ROWS=40000
FACTOR_NODES=512
FACTOR_ROWS=20000


def ground_proof():
    return dict(schema='qkf-ground-dag-v1',source_hash=kernel.digest(reconstruction.ground_source()),
                nodes=[dict(kind='input',equation=0),dict(kind='input',equation=1),dict(kind='trans',left=0,right=1)],root=2)


def v5_tail(source,budget):
    """The v5 plan, retaining the shared budget and its failed attempts."""
    planned,omitted=prefix.candidates(source);record=budget.record
    record.update(planned_prefix_candidates=len(planned),omitted_prefix_candidates=omitted)
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
    record.update(accepted_prefix_lemmas=len(lemmas),prefix_rewrite_steps=len(trace))
    if tail is None:
        record['partial_prefix_certificate']=dict(lemmas=lemmas,ground_certificate=ground,
                                                  residual_hash=kernel.digest(transformed),rewrite_trace=trace)
        return None,status
    return dict(schema=prefix.SCHEMA,source_hash=kernel.digest(source),lemmas=lemmas,ground_certificate=ground,
                residual_hash=kernel.digest(transformed),rewrite_trace=trace,tail_backend=backend,tail=tail),status


def produce(source,checkpoint=lambda record:None):
    start=time.perf_counter();planned,omitted=reconstruction.candidates(source)
    if not planned:return v5_produce(source,checkpoint)
    budget=Budget(checkpoint);record=budget.record
    record.update(planned_reconstruction_candidates=len(planned),omitted_reconstruction_candidates=omitted,
                  reconstruction_candidates=[],factor_attempts=[])
    record['budgets'].update(instance_nodes=INSTANCE_NODES,instance_rows=INSTANCE_ROWS,factor_nodes=FACTOR_NODES,factor_rows=FACTOR_ROWS)
    probe,status=budget.search(source,'reconstruction_probe',node_limit=PROBE_NODES,row_limit=PROBE_ROWS,max_level=0)
    record['reconstruction_probe_status']=status
    if probe is not None:
        record.update(status=status,accepted_reconstruction_lemmas=0,producer_seconds=time.perf_counter()-start)
        return probe,record
    lemmas=[];factors={};attempted={}
    for i,candidate in enumerate(planned):
        try:problem=reconstruction.instance_source(source,candidate)
        except ValueError as error:
            record['reconstruction_candidates'].append(dict(candidate_hash=candidate['candidate_hash'],status='capture_syntax_unsupported',reason=str(error)));continue
        cert,status=budget.search(problem,'reconstruction_instance',i,INSTANCE_NODES,INSTANCE_ROWS)
        record['reconstruction_candidates'].append(dict(candidate_hash=candidate['candidate_hash'],status=status))
        if cert is None:continue
        direction=candidate['descriptor']['direction']
        if direction not in attempted:
            proof,fs=budget.search(reconstruction.factor_source(direction),'universal_factor',direction,FACTOR_NODES,FACTOR_ROWS)
            attempted[direction]=proof
            record['factor_attempts'].append(dict(direction=direction,status=fs))
        if attempted[direction] is None:continue
        factors[direction]=attempted[direction]
        lemmas.append(dict(candidate_hash=candidate['candidate_hash'],candidate=candidate,
                           substitution=reconstruction.substitution(candidate),instance_certificate=cert))
    transformed,trace=reconstruction.residual(source,lemmas)
    tail,status=v5_tail(transformed,budget)
    record.update(status=status,accepted_reconstruction_lemmas=len(lemmas),reconstruction_rewrite_steps=len(trace),
                  producer_seconds=time.perf_counter()-start)
    if tail is None:
        record['partial_reconstruction_certificate']=dict(lemmas=lemmas,factor_certificates=factors,
                        ground_certificate=ground_proof() if lemmas else None,residual_hash=kernel.digest(transformed),rewrite_trace=trace)
        raise Incomplete(record)
    if not lemmas:return tail,record
    return dict(schema=reconstruction.SCHEMA,source_hash=kernel.digest(source),lemmas=lemmas,factor_certificates=factors,
                ground_certificate=ground_proof(),residual_hash=kernel.digest(transformed),rewrite_trace=trace,tail=tail),record
