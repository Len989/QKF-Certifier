"""Produce the fixed Graal create joint-carrier proof after fresh region proofs."""

from .composition_spec import dependency_spec
from .create_kernel import CARRIER, DERIVATION, ROLES, SCHEMA, binding, check
from .model import digest


def synthesize(source, spec):
    from .run_producer import verify

    packages = {}
    for role in ROLES:
        result, package = verify(source, dependency_spec(role), profile=role)
        if package is None:
            return {
                "status": result["status"],
                "stage": role + "_dependency",
                "detail": result,
                "certificate": None,
            }
        packages[role] = package

    certificate = {
        "schema": SCHEMA,
        "binding": binding(source, spec),
        "dependencies": packages,
        "dependencies_sha256": digest(packages),
        "carrier": CARRIER,
        "derivation": DERIVATION,
    }
    result = check(source, spec, certificate)
    return {"status": "candidate", "certificate": certificate, "result": result}
