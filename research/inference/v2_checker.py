"""Independent replay for richer observation inference v2."""

from research.observations.model import digest, require
from research.inference.adapters import blocks_for, conflict, quotient_cells
from .v2_adapters import LIBRARY, System
from .v2_target_checker import check_target_proof

SCHEMA = "qkf-observation-inference-v2"


def _state(value):
    require(type(value) is list and all(type(x) in {int, bool} for x in value),
            "v2 inference witness residual state")
    return tuple(value)


def check(source, target, certificate):
    system = System(source, target)
    require(type(certificate) is dict and set(certificate) == {
        "schema", "binding", "refinements", "pruning", "selected", "blocks", "target_proof"
    } and certificate["schema"] == SCHEMA, "observation inference v2 certificate fields")
    require(digest(certificate["binding"]) == digest(system.binding),
            "inference v2 source/target/library binding")

    selected = []
    refinements = certificate["refinements"]
    require(type(refinements) is list and len(refinements) <= len(system.features),
            "bounded v2 refinement trace")
    for row in refinements:
        require(type(row) is dict and set(row) == {"feature", "conflict"},
                "v2 refinement record")
        issue = conflict(system, selected)
        require(issue is not None and digest(issue) == digest(row["conflict"]),
                "v2 refinement must answer current conflict")
        fid = row["feature"]
        require(type(fid) is str and fid in system.feature_by_id and fid not in selected,
                "fresh v2 library observation")
        left, right = _state(issue["left"]), _state(issue["right"])
        require(system.feature_value(fid, left) != system.feature_value(fid, right),
                "v2 refinement does not separate witness")
        selected.append(fid)
    require(conflict(system, selected) is None, "v2 refinement did not reach stability")

    pruning = certificate["pruning"]
    require(type(pruning) is list, "v2 pruning trace")
    current = list(selected)
    for row in pruning:
        require(type(row) is dict and set(row) in (
            {"feature", "removed"}, {"feature", "removed", "conflict"}
        ), "v2 pruning record")
        fid = row["feature"]
        require(fid in current and type(row["removed"]) is bool, "v2 pruning selected feature")
        trial = [x for x in current if x != fid]
        issue = conflict(system, trial)
        if row["removed"]:
            require(set(row) == {"feature", "removed"} and issue is None,
                    "v2 removed feature must be redundant")
            current = trial
        else:
            require(set(row) == {"feature", "removed", "conflict"} and issue is not None
                    and digest(row["conflict"]) == digest(issue),
                    "v2 retained feature requires instability witness")

    require(certificate["selected"] == current, "final v2 observation set")
    require(conflict(system, current) is None, "final v2 quotient stability")
    blocks, _block_of, cells = quotient_cells(system, current)
    require(certificate["blocks"] == [[list(s) for s in block] for block in blocks],
            "v2 inferred quotient partition")

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
        "selection": "counterexample-guided richer residual refinement with deletion pruning",
        **target_result,
        "scope": (
            "source-derived finite equality/order/relational residual library; "
            "not arbitrary observation-language synthesis"
        ),
    }
