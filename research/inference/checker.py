"""Replay observation-interface inference without running refinement search."""

from research.observations.model import digest, require
from .adapters import System, blocks_for, conflict, quotient_cells
from .target_checker import check_target_proof

SCHEMA = "qkf-observation-inference-v1"


def _state(value):
    require(type(value) is list and all(type(x) in {int, bool} for x in value),
            "inference witness residual state")
    return tuple(value)


def _splits(system, feature_id, left, right):
    return system.feature_value(feature_id, left) != system.feature_value(feature_id, right)


def check(source, target, certificate):
    system = System(source, target)
    require(type(certificate) is dict and set(certificate) == {
        "schema", "binding", "refinements", "pruning", "selected", "blocks", "target_proof"
    } and certificate["schema"] == SCHEMA, "observation inference certificate fields")
    require(digest(certificate["binding"]) == digest(system.binding), "inference source/target/library binding")

    selected = []
    refinements = certificate["refinements"]
    require(type(refinements) is list and len(refinements) <= len(system.features),
            "bounded refinement trace")
    for row in refinements:
        require(type(row) is dict and set(row) == {"feature", "conflict"}, "refinement record")
        current = conflict(system, selected)
        require(current is not None and digest(current) == digest(row["conflict"]),
                "refinement must answer the current conflict")
        fid = row["feature"]
        require(type(fid) is str and fid in system.feature_by_id and fid not in selected,
                "fresh library observation")
        left, right = _state(current["left"]), _state(current["right"])
        require(_splits(system, fid, left, right), "refinement observation does not separate witness")
        selected.append(fid)
    require(conflict(system, selected) is None, "greedy refinement trace did not reach stability")

    pruning = certificate["pruning"]
    require(type(pruning) is list, "pruning trace")
    current_selected = list(selected)
    for row in pruning:
        require(type(row) is dict and set(row) in (
            {"feature", "removed"}, {"feature", "removed", "conflict"}
        ), "pruning record")
        fid = row["feature"]
        require(fid in current_selected and type(row["removed"]) is bool, "pruning selected feature")
        trial = [x for x in current_selected if x != fid]
        issue = conflict(system, trial)
        if row["removed"]:
            require(set(row) == {"feature", "removed"} and issue is None,
                    "removed feature must be behaviorally redundant")
            current_selected = trial
        else:
            require(set(row) == {"feature", "removed", "conflict"} and issue is not None
                    and digest(row["conflict"]) == digest(issue),
                    "retained feature needs a concrete instability witness")

    require(certificate["selected"] == current_selected, "final inferred observation set")
    require(conflict(system, current_selected) is None, "final inferred quotient stability")

    blocks, _block_of, cells = quotient_cells(system, current_selected)
    expected_blocks = [[list(s) for s in block] for block in blocks]
    require(certificate["blocks"] == expected_blocks, "inferred quotient partition")

    target = check_target_proof(system, current_selected, certificate["target_proof"])
    return {
        "status": "certified" if target["target_status"] != "refuted" else "refuted",
        "family": system.family,
        "native_states": len(system.states),
        "candidate_observations": len(system.features),
        "selected_observations": len(current_selected),
        "selected": [
            {"id": fid, "label": system.feature_by_id[fid]["label"]}
            for fid in current_selected
        ],
        "classes": len(blocks),
        "checked_source_edges": len(cells),
        "source_interface": "stable",
        "selection": "counterexample-guided residual-coordinate refinement with deletion pruning",
        **target,
        "scope": (
            "source-derived residual semantics and fixed candidate library; "
            "not arbitrary observation-language synthesis"
        ),
    }
