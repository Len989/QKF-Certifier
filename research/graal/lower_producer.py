"""Construct the source-bound conditional lower proof from independent lemmas."""
from lower_source import compile_source
from carry_producer import produce as produce_carry
from sweep_producer import produce as produce_sweep
from lower_order import obligations,CONCLUSION
from lower_kernel import SCHEMA,replay

def produce(source):
    compiled=compile_source(source);sweep=produce_sweep(compiled['sweep_guard'])
    if sweep['status']!='certificate_produced':return dict(status='sweep_counterexample',details=sweep)
    carry=produce_carry(compiled['carry_program'])
    if carry['status']!='certificate_produced':return dict(status='carry_counterexample',details=carry)
    outer=dict(schema='qkf-lower-order-gluing-v1',ir=compiled['outer_ir'],obligations=obligations(compiled['outer_ir']),conclusion=CONCLUSION)
    c=dict(schema=SCHEMA,compiled_source=compiled,sweep=sweep['certificate'],successor=carry['certificate'],outer=outer,contract=CONCLUSION)
    replay(source,c)
    return dict(status='certificate_produced',certificate=c)
