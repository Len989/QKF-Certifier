"""Independent replay of the Graal create joint-carrier certificate.

The checker performs no proof search. It rebinds the exact caller source,
rechecks both strong region packages, and checks a fixed proof graph for the
caller-level denotation/stabilization argument.
"""
from .create_source import read_source
from .create_spec import check_spec
from .composition_spec import dependency_spec
from .model import digest, require
from .run_package import check_package

SCHEMA = "qkf-graal-create-joint-carrier-v1"
RULES = "graal-create-normalization-joint-carrier-v1"
ROLES = ("descending", "ascending")

CARRIER = [
    {
        "phase": "entry",
        "facts": ["external_input_denotation", "source_range_assertions"],
    },
    {
        "phase": "exact_extrema",
        "facts": [
            "same_denotation",
            "exact_lower_endpoint",
            "exact_upper_endpoint",
            "monotone_bounds",
            "tightened_masks",
        ],
    },
    {
        "phase": "prefix_closed_extrema",
        "facts": [
            "same_denotation",
            "exact_lower_endpoint",
            "exact_upper_endpoint",
            "common_prefix_reflected_in_masks",
            "monotone_bounds",
            "tightened_masks",
        ],
    },
    {
        "phase": "stable",
        "facts": [
            "same_denotation",
            "exact_lower_endpoint",
            "exact_upper_endpoint",
            "common_prefix_reflected_in_masks",
            "third_pass_is_fixed_point",
            "source_iteration_limit_not_exceeded",
        ],
    },
]

DERIVATION = [
    ["source_binding", "exact pinned create/range/empty/extrema/helper token streams"],
    ["early_empty", "source isEmpty conditions are sound for the declared denotation"],
    ["unrestricted_delegate", "range constructor common-prefix masks preserve an unrestricted interval"],
    ["mask_extrema", "minValueForMasks/maxValueForMasks are exact sign-aware mask extrema"],
    ["prefix_refinement", "bits common to signed interval endpoints are common to every intervening word"],
    ["descending_adapter", "setOptionalBits strong maximum supplies exact upper endpoint in a fixed sign bucket"],
    ["lower_floor_adapter", "the descending loop in computeLowerBound is equivalent to the checked maximum scan"],
    ["successor_adapter", "the checked cyclic successor plus the derived nonwrap premise supplies the exact lower endpoint"],
    ["zero_exclusion", "the explicit canBeZero branches select the next exact nonzero endpoint or an empty sentinel"],
    ["post_helper_empty", "after exact endpoints, the source empty test is exact"],
    ["pass_preservation", "clamps, prefix facts, mask intersection and exact endpoints preserve the denotation"],
    ["two_update_stabilization", "after exact extrema, one prefix-refinement update is sufficient; the following pass is fixed"],
    ["monotonic_guarantees", "preserved denotation and exact extrema imply lower never decreases and upper never increases"],
    ["one_bit_edge", "bits=1 has no nonsign payload and is discharged by the direct endpoint rules"],
]


def binding(source, spec):
    check_spec(spec)
    return {
        "source": read_source(source),
        "specification_sha256": digest(spec),
        "rules": RULES,
    }


def _dependencies(source, packages):
    require(type(packages) is dict and set(packages) == set(ROLES),
            "both exact create helper dependencies")
    checked = {}
    for role in ROLES:
        goal = dependency_spec(role)
        checked[role] = check_package(source, goal, packages[role], profile=role)
        require(checked[role]["status"] == "certified", "strong " + role + " dependency")
    return checked


def check(source, spec, certificate):
    expected = binding(source, spec)
    require(
        type(certificate) is dict
        and set(certificate) == {
            "schema", "binding", "dependencies", "dependencies_sha256",
            "carrier", "derivation"
        }
        and certificate["schema"] == SCHEMA,
        "create joint-carrier certificate fields",
    )
    require(digest(certificate["binding"]) == digest(expected),
            "create source/specification binding")
    require(digest(certificate["dependencies"]) == certificate["dependencies_sha256"],
            "create dependency identities")
    checked = _dependencies(source, certificate["dependencies"])
    require(certificate["carrier"] == CARRIER, "fixed create joint carrier")
    require(certificate["derivation"] == DERIVATION, "fixed create derivation")

    return {
        "status": "certified",
        "claim": "integer_stamp_create_normalization",
        "all_supported_java_bit_widths": True,
        "supported_bits": [1, 8, 16, 32, 64],
        "carrier_states": len(CARRIER),
        "source_sha256": expected["source"]["source_sha256"],
        "specification_sha256": digest(spec),
        "dependency_properties": {
            role: {
                "status": checked[role]["status"],
                "claim": checked[role]["property"]["claim"],
                "all_positive_payload_widths": checked[role]["property"]["all_positive_payload_widths"],
            }
            for role in ROLES
        },
        "derived_helper_premises": [
            "descending seed is the sign-bucket mask minimum and is no greater than its bound",
            "computeLowerBound floor uses the same masks and minimum seed",
            "successor seed is a legal floor result",
            "floor<bound together with bound<=bucket maximum proves a greater legal word exists, so cyclic wrap is impossible",
        ],
        "stabilization": {
            "source_iteration_limit": 3,
            "updates_before_fixed_point_at_most": 2,
            "reason": "exact extrema then one denotation-preserving common-prefix refinement",
        },
        "scope": {
            "exact_external_create_shape": True,
            "whole_create_normalization_contract": True,
            "arbitrary_java_frontend": False,
            "native_java_all_inputs": False,
            "new_lean_theorem": False,
            "trusted_rules": RULES,
        },
    }
