"""Compact already checked PR35/36 packages. Discovery remains the old producer.

This reduces portable representation, not the number of states discovered or
transient allocation of legacy source certificates during production.
"""
from research.observations.model import require
from research.signed_context.io import freeze, thaw
from research.signed_context.session import load as old_load, shape
from research.signed_targets.common import prepare
from .checker import SCHEMA, SOURCE_SCHEMA, load
from . import dag, finite


def pack_proofs(source, targets, proofs):
    require(type(targets) is list and type(proofs) is list and 0 < len(targets) == len(proofs) <= 64,
            '1..64 complete independently targeted proofs')
    # Each supplied old proof is checked BEFORE dropping its old explicit witnesses.
    targets = thaw(freeze(targets))
    selection = prepare(targets[0])[1]
    source_proof = thaw(freeze(shape(proofs[0])['observations']))
    ctx = old_load(source, selection, source_proof)
    items = []
    for target, proof in zip(targets, proofs):
        ctx.check(target, proof)  # Also requires the exact same source dependency.
        items.append({'target': target, 'obligation': thaw(freeze(proof['proof']['obligation']))})
    source_proof['schema'] = SOURCE_SCHEMA
    obs = source_proof['observations']; obs.pop('separators')
    obs['schema'] = finite.SCHEMA; obs['separation'] = finite.POLICY
    packet = dag.pack({'schema': SCHEMA, 'selection': selection, 'source': source_proof, 'items': items})
    verified = load(source, targets, packet)
    return verified.results(), packet


def prove_many(source, targets, *, budgets=None):
    from research.unified.v7 import batch
    _, pairs = batch(source, targets, budgets=budgets)
    if any(proof is None for _, proof in pairs):
        return [result for result, _ in pairs], None  # No partial aggregate proof.
    return pack_proofs(source, targets, [proof for _, proof in pairs])
