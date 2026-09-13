"""Produce a source-bound all-input certificate or a finite separating case."""
from source_contract import compile_source
from sweep_producer import produce as sweep_produce
from order_kernel import evaluate
from universal_kernel import SCHEMA,CONTRACT,replay


def produce(source):
    compiled=compile_source(source);sweep=sweep_produce(compiled['sweep']['guard'])
    if sweep['status']!='certificate_produced':return dict(status='sweep_counterexample',evidence=sweep)
    order=evaluate(compiled['upper']['ir'])
    if order['status']!='proved_all_order_types':return dict(status='order_counterexample',evidence=order)
    c=dict(schema=SCHEMA,contract=CONTRACT,compiled_source=compiled,
           sweep_certificate=sweep['certificate'],order_certificate=order)
    replay(source,c)
    return dict(status='certificate_produced',certificate=c)
