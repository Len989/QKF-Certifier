"""Replay local equalities and exact dependency slicing, without producer search."""
from research.observations.model import digest, require
from research.signed_bridge.model import read
from .rules import MAX_STEPS, SCHEMA, binding, compact, rewrite, validate_formula


def rebuild(source, selection, certificate):
    require(type(certificate) is dict and set(certificate) == {
        "schema", "binding", "original_ir", "steps", "final_formula", "projection", "reduced_ir"
    } and certificate["schema"] == SCHEMA, "source reduction certificate fields")
    ir = read(source, selection)  # Entire body must be supported, including dead statements.
    require(digest(certificate["binding"]) == digest(binding(selection, ir))
            and digest(certificate["original_ir"]) == digest(ir), "original source/IR binding")
    steps = certificate["steps"]
    require(type(steps) is list and len(steps) <= MAX_STEPS, "bounded reduction trace")
    formula = ir["formula"]
    validate_formula(formula, len(ir["atoms"]))
    for instruction in steps:
        formula = rewrite(ir, formula, instruction)
    require(digest(formula) == digest(certificate["final_formula"]), "replayed final formula")
    reduced, projection = compact(ir, formula)
    require(digest(projection) == digest(certificate["projection"]), "exact live dependency projection")
    require(digest(reduced) == digest(certificate["reduced_ir"]), "reconstructed reduced IR")
    return ir, reduced


def check(source, selection, certificate):
    original, reduced = rebuild(source, selection, certificate)
    return {"schema": "qkf-signed-source-reduction-result-v1", "status": "source_reduction_verified",
            "claim": "source_reduced_ir_equivalence", "source_sha256": original["source_sha256"],
            "request_sha256": digest(selection), "reduced_ir_sha256": digest(reduced),
            "checked_steps": len(certificate["steps"]),
            "word_nodes_before": len(original["nodes"]), "word_nodes_after": len(reduced["nodes"]),
            "atoms_before": len(original["atoms"]), "atoms_after": len(reduced["atoms"]),
            "residual_coordinates_before": len(original["nodes"]) + 2 * len(original["atoms"]),
            "residual_coordinates_after": len(reduced["nodes"]) + 2 * len(reduced["atoms"]),
            "original_states_enumerated": 0, "all_positive_widths_in_declared_profile": True,
            "target_checked": False, "lean_checked": False,
            "scope": "typed local equalities and exact slicing under retained pure total signed semantics; "
                     "not a target proof, canonical normal form or general Java optimizer"}
