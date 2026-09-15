"""Common research proof envelope. Replay imports no producer or native harness.

The external specification selects one of two fixed profiles. Package data
cannot select Python modules, files, premises or a weaker target. The two
embedded certificates keep their existing schemas and are replayed by their
original checkers. This layer establishes no new source-language theorem.
"""
import hashlib

from .model import digest

SCHEMA = "qkf-research-package-v1"
RESULT_SCHEMA = "qkf-research-run-result-v1"
EXIT_CODES = {
    "certified": 0, "refuted": 1, "budget_exhausted": 2,
    "invalid_certificate": 3, "unsupported": 4,
    "input_error": 64, "internal_error": 70,
}
DEPENDENCIES = {
    "source": ["external_source"],
    "property": ["external_source", "source", "external_specification"],
}
PROFILES = {
    "descending": {
        "source_schema": "qkf-source-derived-factor-v1",
        "property_schema": "qkf-masked-upper-property-v1",
        "specification_schema": "qkf-masked-upper-spec-v1",
        "source_claim": "source_model_equivalence",
        "semantics": "restricted unsigned descending single-bit OR helper; extra zero sign bit",
    },
    "ascending": {
        "source_schema": "qkf-ascending-source-factor-v1",
        "property_schema": "qkf-masked-successor-property-v1",
        "specification_schema": "qkf-masked-successor-spec-v1",
        "source_claim": "source_region_model_equivalence",
        "semantics": "restricted unsigned ascending source region; emitted low payload bits only",
    },
}
VALIDATION_ERRORS = (ValueError, TypeError, KeyError, IndexError, RecursionError)


class RunError(Exception):
    def __init__(self, status, stage, message):
        super().__init__(message)
        self.status, self.stage = status, stage

    def result(self):
        return {"schema": RESULT_SCHEMA, "status": self.status,
                "stage": self.stage, "error": str(self)}


def profile_for(spec, requested=None):
    """The caller's goal, never the package, determines the replay profile."""
    if type(spec) is not dict or type(spec.get("schema")) is not str:
        raise RunError("input_error", "specification", "a versioned external specification is required")
    profiles = [name for name, value in PROFILES.items()
                if value["specification_schema"] == spec["schema"]]
    if len(profiles) != 1:
        raise RunError("input_error", "specification", "unsupported specification schema")
    profile = profiles[0]
    if requested is not None and (type(requested) is not str or requested != profile):
        raise RunError("input_error", "profile", "profile conflicts with the external specification")
    if profile == "ascending":
        from .successor_spec import check_spec
    else:
        from .upper_spec import check_spec
    try:
        check_spec(spec)
    except VALIDATION_ERRORS as exc:
        raise RunError("input_error", "specification", str(exc)) from exc
    return profile


def source_text(source):
    if type(source) is not str:
        raise RunError("input_error", "source", "source must be exact UTF-8 text")
    try:
        source.encode("utf-8")
    except UnicodeError as exc:
        raise RunError("input_error", "source", "source is not valid UTF-8") from exc


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _binding(source, spec, source_certificate, property_certificate):
    return {
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "specification_sha256": digest(spec),
        "source_certificate_sha256": digest(source_certificate),
        "property_certificate_sha256": digest(property_certificate),
    }


def _checked_result(source, spec, profile, source_certificate, property_certificate):
    if profile == "ascending":
        from .ascending_kernel import check as check_source
        from .successor_kernel import check as check_property
        expected_claim = "masked_" + spec["claim"]
    else:
        from .source_factor import check as check_source
        from .property_kernel import check as check_property
        expected_claim = "masked_upper_" + spec["claim"]
    contract = PROFILES[profile]
    _require(type(source_certificate) is dict
             and source_certificate.get("schema") == contract["source_schema"], "source certificate schema")
    _require(type(property_certificate) is dict
             and property_certificate.get("schema") == contract["property_schema"], "property certificate schema")
    model = check_source(source, source_certificate)
    goal = check_property(source, source_certificate, spec, property_certificate)
    _require(model.get("status") == "certified" and model.get("claim") == contract["source_claim"],
             "source-model claim is separate from the target")
    _require(goal.get("status") in {"certified", "refuted"} and goal.get("claim") == expected_claim,
             "complete independently checked target verdict")
    _require(goal.get("all_positive_payload_widths") is (goal["status"] == "certified"),
             "positive all-width proof and concrete refutation scopes")
    return {
        "schema": RESULT_SCHEMA, "status": goal["status"], "profile": profile,
        "claim": expected_claim, "source_model": model, "property": goal,
        "scope": {
            "semantics": contract["semantics"],
            "all_positive_payload_widths": goal["all_positive_payload_widths"],
            "trusted_frontend_and_slice_rules": True,
            "whole_computeLowerBound_or_create": False,
            "native_java_all_widths": False, "new_lean_theorem": False,
        },
    }


def check_package(source, spec, package, *, profile=None):
    """Recompute the verdict; reject changed summaries as well as changed proofs."""
    source_text(source)
    selected = profile_for(spec, profile)
    try:
        _require(type(package) is dict and set(package) == {
            "schema", "profile", "contracts", "binding", "dependencies", "proofs", "result"
        }, "research package fields")
        _require(package["schema"] == SCHEMA and package["profile"] == selected,
                 "package schema and externally selected profile")
        _require(digest(package["contracts"]) == digest(PROFILES[selected]), "semantic contract identifiers")
        _require(digest(package["dependencies"]) == digest(DEPENDENCIES), "fixed proof dependency graph")
        proofs = package["proofs"]
        _require(type(proofs) is dict and set(proofs) == {"source", "property"}, "two embedded proofs")
        _require(digest(package["binding"]) == digest(_binding(source, spec, proofs["source"], proofs["property"])),
                 "external source, goal and embedded-proof bindings")
        result = _checked_result(source, spec, selected, proofs["source"], proofs["property"])
        _require(digest(package["result"]) == digest(result), "saved result differs from independent replay")
        return result
    except VALIDATION_ERRORS as exc:
        raise RunError("invalid_certificate", "package_replay", str(exc)) from exc


def create_package(source, spec, profile, source_certificate, property_certificate):
    """Wrap existing proofs only after replay. This does not run proof search."""
    source_text(source)
    selected = profile_for(spec, profile)
    try:
        result = _checked_result(source, spec, selected, source_certificate, property_certificate)
        return {
            "schema": SCHEMA, "profile": selected, "contracts": dict(PROFILES[selected]),
            "binding": _binding(source, spec, source_certificate, property_certificate),
            "dependencies": {key: list(value) for key, value in DEPENDENCIES.items()},
            "proofs": {"source": source_certificate, "property": property_certificate}, "result": result,
        }
    except VALIDATION_ERRORS as exc:
        raise RunError("invalid_certificate", "package_creation", str(exc)) from exc


def explain_package(source, spec, package, *, profile=None):
    """Explain a freshly checked result, not untrusted package assertions."""
    result = check_package(source, spec, package, profile=profile)
    goal = result["property"]
    explanation = {
        "replayed": True,
        "chain": [
            {"step": "source_model", "claim": result["source_model"]["claim"], "status": "certified"},
            {"step": "independent_target", "claim": goal["claim"], "status": goal["status"]},
        ],
        "preconditions": spec["preconditions"], "obligations": spec["obligations"],
        "basis": ("closed observation under every legal column; mathematical word induction"
                  if result["status"] == "certified" else
                  "concrete witness replayed by source factor, integer source and integer target"),
        "limitations": [
            "the frontend, slice rules and target rules remain trusted",
            "no full signed JVM, surrounding computeLowerBound or create proof",
            "no new Lean theorem or installed-package capability",
        ],
    }
    if result["status"] == "refuted":
        explanation.update(reason=goal["reason"], counterexample=goal["counterexample"])
    else:
        explanation.update(closed_states=goal["closed_states"],
                           checked_transitions=goal["checked_transitions"])
    return {**result, "explanation": explanation}
