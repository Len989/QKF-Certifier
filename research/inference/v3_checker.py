"""Independent replay for richer observation inference v3."""

from research.observations.model import digest, require
from research.inference.adapters import conflict, quotient_cells
from .v3_adapters import LIBRARY, System
from .v3_target_checker import check_target_proof

SCHEMA = "qkf-observation-inference-v3"


def _state(value):
    require(type(value) is list and all(type(x) in {int, bool} for x in value),
            "v3 inference witness residual state")
    return tuple(value)


def check(source, target, certificate):
    system = System(source, target)
    require(type(certificate) is dict and set(certificate) == {
        "schema", "binding", "refinements", "pruning", "selected", "blocks", "target_proof"
    } and certificate["schema"] == SCHEMA, "observation inference v3 certificate fields")
    require(digest(certificate["binding"]) == digest(system.binding),
            "inference v3 source/target/library binding")

    selected = []
    refinements = certificate["refinements"]
    require(type(refinements) is list and len(refinements) <= len(system.features),
            "bounded v3 refinement trace")
    for row in refinements:
        require(type(row) is dict and set(row) == {"feature", "conflict"},
                "v3 refinement record")
        issue = conflict(system, selected)
        require(issue is not None and digest(issue) == digest(row["conflict"]),
                "v3 refinement must answer current conflict")
        fid = row["feature"]
        require(type(fid) is str and fid in system.feature_by_id and fid not in selected,
                "fresh v3 library observation")
        left, right = _state(issue["left"]), _state(issue["right"])
        require(system.feature_value(fid, left) != system.feature_value(fid, right),
                "v3 refinement does not separate witness")
        selected.append(fid)
    require(conflict(system, selected) is None, "v3 refinement did not reach stability")

    pruning = certificate["pruning"]
    require(type(pruning) is list and len(pruning) <= len(refinements) * (len(refinements) + 1),
            "bounded v3 pruning trace")
    current = list(selected)
    for row in pruning:
        require(type(row) is dict and set(row) in (
            {"feature", "removed"}, {"feature", "removed", "conflict"}
        ), "v3 pruning record")
        fid = row["feature"]
        require(fid in current and type(row["removed"]) is bool, "v3 pruning selected feature")
        trial = [x for x in current if x != fid]
        issue = conflict(system, trial)
        if row["removed"]:
            require(set(row) == {"feature", "removed"} and issue is None,
                    "v3 removed feature must be redundant")
            current = trial
        else:
            require(set(row) == {"feature", "removed", "conflict"} and issue is not None
                    and digest(row["conflict"]) == digest(issue),
                    "v3 retained feature requires instability witness")

    require(type(certificate["selected"]) is list and certificate["selected"] == current,
            "final v3 observation set")
    # Replay does not trust the producer's pruning/minimality claim.
    for fid in current:
        require(conflict(system, [x for x in current if x != fid]) is not None,
                "v3 selected set must be single-deletion irredundant")
    require(conflict(system, current) is None, "final v3 quotient stability")
    blocks, _block_of, cells = quotient_cells(system, current)
    require(digest(certificate["blocks"]) == digest([[list(s) for s in block] for block in blocks]),
            "v3 inferred quotient partition")

    target_result = check_target_proof(system, current, certificate["target_proof"])
    return {
        "status": "refuted" if target_result["target_status"] == "refuted" else "certified",
        "family": system.family,
        "candidate_library": LIBRARY,
        "native_states": len(system.states),
        "candidate_observations": len(system.features),
        "selected_observations": len(current),
        "selected": [
            {
                "id": fid,
                "kind": system.feature_by_id[fid]["kind"],
                "label": system.feature_by_id[fid]["label"],
            }
            for fid in current
        ],
        "classes": len(blocks),
        "checked_source_edges": len(cells),
        "source_interface": "stable",
        "single_deletion_irredundant": True,
        "selection": "counterexample-guided richer residual refinement with deletion pruning",
        **target_result,
        "scope": (
            "source-derived bounded terminal continuations plus finite equality/order/relational residual library; "
            "not arbitrary observation-language synthesis"
        ),
    }
