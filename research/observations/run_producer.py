"""Common orchestration of the existing source and independent-target producers.

Only verify imports this module. Profile-specific semantics and certificate
schemas are unchanged. Search budgets are a caller input, never a premise of
a successful proof. An exhausted search emits no research proof package.
"""
from .run_package import (RESULT_SCHEMA, RunError, TYPED_SPEC, VALIDATION_ERRORS,
                          check_package, create_package, profile_for, source_text)

# (default, minimum, maximum); other source/factor limits remain inherited.
LIMITS = {
    "ascending": {
        "source": {"max_states": (64, 1, 64), "max_offset": (255, 0, 255),
                   "max_observations": (63, 0, 63), "max_pullbacks": (4096, 0, 100000),
                   "max_classes": (64, 1, 64)},
        "property": {"max_states": (8192, 1, 8192), "max_witness": (256, 1, 256)},
    },
    "descending": {
        "source": {"max_contexts": (8, 1, 8), "max_actions": (16, 1, 16)},
        "property": {"max_states": (8192, 1, 8192)},
    },
}


def budgets_for(profile, budgets):
    if budgets is None:
        budgets = {}
    if type(budgets) is not dict or set(budgets) - {"source", "property"}:
        raise RunError("input_error", "budget", "budget object accepts source and property sections only")
    resolved = {}
    for stage, limits in LIMITS[profile].items():
        supplied = budgets.get(stage, {})
        if type(supplied) is not dict or set(supplied) - set(limits):
            raise RunError("input_error", "budget", "unsupported budget key for " + profile + "/" + stage)
        resolved[stage] = {}
        for name, (default, lower, upper) in limits.items():
            value = supplied.get(name, default)
            if type(value) is not int or not lower <= value <= upper:
                raise RunError("input_error", "budget", "invalid budget: " + stage + "/" + name)
            resolved[stage][name] = value
    return resolved


def _proposal(proposal, profile, stage):
    if type(proposal) is not dict:
        raise RunError("internal_error", stage, "producer returned a non-object")
    if proposal.get("status") == "budget_exhausted" and proposal.get("certificate") is None:
        return {"schema": RESULT_SCHEMA, "status": "budget_exhausted", "profile": profile,
                "stage": stage, "reason": str(proposal.get("reason", "producer budget")),
                "detail_stage": str(proposal.get("stage", stage)), "package": None}
    if proposal.get("status") != "candidate" or type(proposal.get("certificate")) is not dict:
        raise RunError("internal_error", stage, "producer must return candidate or exhaustion without proof")
    return None


def verify(source, spec, *, profile, budgets=None):
    """Return (fresh checked result, package or None). Errors raise RunError."""
    source_text(source)
    selected = profile_for(spec, profile)
    limits = budgets_for(selected, budgets)
    if selected == "ascending":
        from .ascending_source import read_source
        from .ascending_producer import synthesize as derive_source
        from .ascending_kernel import check as check_source
    else:
        from .java_words import read_source
        from .source_factor import synthesize as derive_source, check as check_source
    if spec["schema"] == TYPED_SPEC:
        from .target_producer import synthesize as derive_property
    elif selected == "ascending":
        from .successor_producer import synthesize as derive_property
    else:
        from .property_producer import synthesize as derive_property
    # Unsupported grammar is a source-profile outcome, not a counterexample.
    try:
        read_source(source)
    except VALIDATION_ERRORS as exc:
        return {"schema": RESULT_SCHEMA, "status": "unsupported", "profile": selected,
                "stage": "source_profile", "reason": str(exc), "package": None}, None
    try:
        source_proposal = derive_source(source, **limits["source"])
        exhausted = _proposal(source_proposal, selected, "source_search")
        if exhausted is not None:
            return exhausted, None
        source_certificate = source_proposal["certificate"]
        source_result = check_source(source, source_certificate)
        if source_result.get("status") != "certified":
            raise RunError("internal_error", "source_replay", "generated source proof was not certified")
        property_proposal = derive_property(source, source_certificate, spec, **limits["property"])
        exhausted = _proposal(property_proposal, selected, "property_search")
        if exhausted is not None:
            return exhausted, None
        package = create_package(source, spec, selected, source_certificate, property_proposal["certificate"])
        return check_package(source, spec, package, profile=selected), package
    except RunError as exc:
        if exc.status == "invalid_certificate":
            raise RunError("internal_error", "generated_proof_replay", str(exc)) from exc
        raise
    except VALIDATION_ERRORS as exc:
        raise RunError("internal_error", "proof_pipeline", str(exc)) from exc
