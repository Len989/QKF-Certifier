"""Compose the accepted bridge and backward-closure producer, without a catalog.

No target, partition, feature list, desired state count or lookahead depth is
accepted. max_classes is a resource ceiling, never a requested quotient size.
The generic producer already supplies atomic rows and row-derived cells; no new
closure or row-completion algorithm is introduced here.
"""
from research.observations.model import MAX_ATOMIC_CLASSES, integer, require
from research.observations.producer import synthesize
from research.signed_bridge.producer import derive as derive_source
from research.signed_bridge.checker import rebuild as rebuild_source
from research.signed_bridge.model import CapacityExceeded, MAX_STATES
from .checker import SCHEMA, binding, check


def derive(source, selection, *, max_states=MAX_STATES, max_observations=63,
           max_pullbacks=4096, max_classes=MAX_ATOMIC_CLASSES):
    require(integer(max_states, 1, MAX_STATES) and integer(max_observations, 0, 63)
            and integer(max_pullbacks, 0, 100000) and integer(max_classes, 1, MAX_ATOMIC_CLASSES),
            "budgets: states 1..64, observations 0..63, pullbacks 0..100000, classes 1..64")
    try:
        bridge, _ = derive_source(source, selection, max_states=max_states)
    except CapacityExceeded as exc:
        return None, {"status": "budget_exhausted", "stage": "source_model",
                      "reason": str(exc), "target_checked": False}
    _, model = rebuild_source(source, selection, bridge)
    proposed = synthesize(model.data, row_encoding="atomic", max_observations=max_observations,
                          max_pullbacks=max_pullbacks, max_classes=max_classes)
    if proposed["status"] == "budget_exhausted":
        return None, {"status": "budget_exhausted", "stage": "observation_closure",
                      "reason": proposed["reason"], "target_checked": False,
                      "discovery": {key: proposed[key] for key in ("observations", "classes", "pullbacks")}}
    require(proposed["status"] == "candidate", "unexpected observation producer outcome")
    certificate = {"schema": SCHEMA, "binding": binding(selection, bridge, model),
                   "source_model": bridge, "observations": proposed["certificate"]}
    # Only the checker creates the successful outer result. Discovery counters
    # describe this run; they are not accepted as proof premises on replay.
    return certificate, {**check(source, selection, certificate),
                         "discovery": {key: proposed[key] for key in ("observations", "classes", "pullbacks")}}
