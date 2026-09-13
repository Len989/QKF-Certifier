"""One source-bound certificate covers every width, compatible mask and upper bound."""
from source_contract import compile_source
from sweep_kernel import replay as replay_sweep
from order_kernel import replay as replay_order
from row_kernel import require,digest

SCHEMA='qkf-universal-source-upper-v1'
CONTRACT=dict(width='every positive mathematical word width',native_widths=[1,8,16,32,64],
              masks='0 <= must,may < 2**width and must & ~may == 0',
              bound='every signed width-bit upper bound',can_zero='either Boolean value',
              nonempty='exact greatest represented word <= bound, excluding zero when requested',
              empty='source minimum-value return with proof of the empty branch; value equality alone is not an emptiness test',
              caller='tightening the upper bound preserves intersection with every additional lower bound')


def replay(source,certificate):
    c=certificate
    require(set(c)=={'schema','contract','compiled_source','sweep_certificate','order_certificate'},'universal certificate fields')
    require(c['schema']==SCHEMA and c['contract']==CONTRACT,'universal input/output contract')
    compiled=compile_source(source)
    require(c['compiled_source']==compiled,'actual source and compiled IR binding')
    sweep=replay_sweep(compiled['sweep']['guard'],c['sweep_certificate'])
    order=replay_order(compiled['upper']['ir'],c['order_certificate'])
    return dict(status='proved_universal_upper_contract',certificate_sha256=digest(c),
                source_sha256=compiled['source_sha256'],contract=CONTRACT,sweep=sweep,
                order={k:v for k,v in order.items() if k!='branch_counts'},
                boundary='Restricted source-to-observation compiler, native signed-mask extrema and CodeUtil semantics; no formal Java compiler or full create theorem')
