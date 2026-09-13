"""Propose source observations using the general interval-redundancy lemma."""
from source_kernel import SCHEMA,CONTRACT,observe_source
from hull_producer import produce_hull


def produce_source(source,operation):
    proofs=[]
    def handler(index,carrier,lower,upper,zero,guards):
        assert index==len(proofs)
        proofs.append(produce_hull(source,carrier,lower,upper,zero,guards))
    observation=observe_source(source,operation,handler)
    return dict(schema=SCHEMA,operation=operation,contract=CONTRACT,source_observation=observation,hull_certificates=proofs)
