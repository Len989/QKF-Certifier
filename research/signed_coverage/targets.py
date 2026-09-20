"""Covered source interfaces explicitly connected to the retained target product.

Product checking and raw-word refutation validation are reused unchanged from
PR31. Only the source-bound loading contract is new. Old formats are not forged.
"""
from copy import deepcopy
from research.observations.model import digest, integer, require
from research.signed_targets.common import Monitor, prepare, binding as old_binding, budgets as old_budgets
from research.signed_targets.checker import check_product, check_witness
from .runtime import load

SCHEMA = "qkf-signed-guarded-target-v1"
ENGINE = "signed-guarded-observation-target-v1"


def budgets(value):
    value = {} if value is None else deepcopy(value)
    require(type(value) is dict, "covered target budget object")
    extra = {k: value.pop(k, default) for k, default in (("max_steps", 512), ("max_local_steps", 4096))}
    require(integer(extra["max_steps"], 0, 512) and integer(extra["max_local_steps"], 0, 4096),
            "reduction and guarded proof budgets")
    return {**old_budgets(value), **extra}


def binding(compiled, receipt):
    return {**old_binding(compiled, receipt), "engine": ENGINE, "source_route": "guarded-coverage-v1"}


def check(source, target, certificate):
    target, certificate = deepcopy(target), deepcopy(certificate)
    compiled, selection = prepare(target)
    require(type(certificate) is dict and set(certificate) == {"schema", "binding", "observations", "obligation"}
            and certificate["schema"] == SCHEMA, "guarded target envelope")
    runner, receipt = load(source, selection, certificate["observations"])
    require(digest(certificate["binding"]) == digest(binding(compiled, receipt)), "covered source/target binding")
    monitor = Monitor(runner, compiled["specification"])
    obligation = certificate["obligation"]
    require(type(obligation) is dict and obligation.get("kind") in {"closure", "counterexample"},
            "covered target obligation")
    verified = (check_product(monitor, obligation) if obligation["kind"] == "closure"
                else check_witness(source, selection, monitor, obligation))
    return {"status": verified["status"], "engine": ENGINE,
            "claim": "source_matches_independent_target_through_guarded_coverage",
            "all_positive_widths": verified["status"] == "certified", "target_checked": True,
            "source_interface_verified": True, "lean_checked": False,
            "runtime": receipt, "target": verified, "target_sha256": compiled["target_sha256"],
            "scope": "retained modular signed profile; trusted frontend, reduction/local simulation, "
                     "target semantics and Python checkers; not new Lean verification"}


def prove(source, target, *, limits=None):
    from .producer import infer
    from research.signed_targets.producer import discover, ProductLimit
    target = deepcopy(target)
    compiled, selection = prepare(target)
    options = budgets(limits)
    observation, outcome = infer(source, selection, **{k: v for k, v in options.items()
                                  if k not in {"max_target_states", "max_witness_bits"}})
    if observation is None:
        return None, {**outcome, "source_interface_verified": False, "target_checked": False}
    runner, receipt = load(source, selection, observation)
    try:
        obligation = discover(Monitor(runner, compiled["specification"]),
                              options["max_target_states"], options["max_witness_bits"])
    except ProductLimit as exc:
        return None, {"status": "budget_exhausted", "stage": "target_product", "reason": str(exc),
                      "source_interface_verified": True, "target_checked": False, "runtime": receipt}
    certificate = {"schema": SCHEMA, "binding": binding(compiled, receipt),
                   "observations": observation, "obligation": obligation}
    return certificate, check(source, target, certificate)
