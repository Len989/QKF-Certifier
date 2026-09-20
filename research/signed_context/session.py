"""One complete PR35 load, many independent targets with no shared reconstruction.

The in-process context is not a serialized proof and not a security boundary
against reflection or monkeypatching. Portable outputs are unchanged PR35 proof
objects: their source dependency is checked in full by a fresh verifier.
"""
from dataclasses import dataclass

from research.observations.model import digest, integer, require
from research.signed_coverage.targets import ENGINE, SCHEMA, binding, budgets as full_budgets
from research.signed_targets.common import Monitor, prepare, MAX_PRODUCT, MAX_WITNESS
from research.signed_targets.checker import check_product
from research.unified.checker import InvalidProof
from research.unified.v3_schema import SIGNED_KIND
from .io import freeze, thaw, source_text
from .witness import check_ir

PROOF_SCHEMA = "qkf-unified-proof-v5"
RESULT_SCHEMA = "qkf-unified-result-v5"
CONTEXT_SCHEMA = "qkf-signed-checked-context-v1"
_KEY = object()
MAX_TARGETS = 64


def target_limits(value):
    value = {} if value is None else thaw(freeze(value))
    require(type(value) is dict and set(value) <= {"max_target_states", "max_witness_bits"},
            "a loaded context accepts target budgets only")
    options = {"max_target_states": MAX_PRODUCT, "max_witness_bits": MAX_WITNESS, **value}
    require(integer(options["max_target_states"], 1, MAX_PRODUCT)
            and integer(options["max_witness_bits"], 0, MAX_WITNESS), "target budgets")
    return options


def shape(envelope):
    require(type(envelope) is dict and set(envelope) == {"schema", "kind", "engine", "proof", "result"}
            and envelope["schema"] == PROOF_SCHEMA and envelope["kind"] == SIGNED_KIND
            and envelope["engine"] == ENGINE, "context accepts an unchanged covered target envelope")
    proof = envelope["proof"]
    require(type(proof) is dict and set(proof) == {"schema", "binding", "observations", "obligation"}
            and proof["schema"] == SCHEMA, "covered target certificate fields")
    return proof


def wrap(inner):
    return {"schema": RESULT_SCHEMA, "status": inner["status"], "kind": SIGNED_KIND,
            "engine": ENGINE, "profile": "signed-guarded-residual-coverage",
            "all_positive_widths": inner.get("all_positive_widths", False),
            "target_checked": inner.get("target_checked", False), "lean_checked": False,
            "inner": inner}


@dataclass(frozen=True, slots=True, init=False)
class CheckedContext:
    """Immutable ordinary-API capability issued only after source proof checking.

    No mutable Model, residual execution state or forward cells drive targets.
    The full source proof and original IR remain as immutable JSON for portable
    export and negative checks; this is deliberately not a proof compression PR.
    """
    _runner: object
    _selection_json: str
    _observations_json: str
    _ir_json: str
    _receipt_json: str

    def __init__(self, key=None, *, runner=None, selection=None, observations=None, ir=None, receipt=None):
        require(key is _KEY, "use source-bound load; a receipt or raw Runner cannot create a checked context")
        for name, value in (("_runner", runner), ("_selection_json", selection),
                            ("_observations_json", observations), ("_ir_json", ir), ("_receipt_json", receipt)):
            object.__setattr__(self, name, value)

    def __reduce_ex__(self, protocol):
        raise TypeError("checked contexts are process-local; export proofs and check again, not pickle")

    def _prepare(self, target):
        compiled, selection = prepare(thaw(freeze(target)))
        require(freeze(selection) == self._selection_json, "target selects a different source entry/type/contract")
        return compiled

    def _check_obligation(self, compiled, obligation):
        require(type(obligation) is dict and obligation.get("kind") in {"closure", "counterexample"},
                "covered target obligation")
        monitor = Monitor(self._runner, compiled["specification"])
        verified = (check_product(monitor, obligation) if obligation["kind"] == "closure"
                    else check_ir(thaw(self._ir_json), thaw(self._selection_json), monitor, obligation))
        # Retain the exact v6 result, including every trust/scope field.
        return wrap({"status": verified["status"], "engine": ENGINE,
            "claim": "source_matches_independent_target_through_guarded_coverage",
            "all_positive_widths": verified["status"] == "certified", "target_checked": True,
            "source_interface_verified": True, "lean_checked": False,
            "runtime": thaw(self._receipt_json), "target": verified, "target_sha256": compiled["target_sha256"],
            "scope": "retained modular signed profile; trusted frontend, reduction/local simulation, "
                     "target semantics and Python checkers; not new Lean verification"})

    def prove(self, target, *, limits=None):
        """Discover/check only a new target product; source proof was checked by load."""
        compiled = self._prepare(target)
        options = target_limits(limits)
        from research.signed_targets.producer import discover, ProductLimit
        try:
            obligation = discover(Monitor(self._runner, compiled["specification"]),
                                 options["max_target_states"], options["max_witness_bits"])
        except ProductLimit as exc:
            return wrap({"status": "budget_exhausted", "stage": "target_product", "reason": str(exc),
                         "source_interface_verified": True, "target_checked": False,
                         "runtime": thaw(self._receipt_json)}), None
        certificate = {"schema": SCHEMA, "binding": binding(compiled, thaw(self._receipt_json)),
                       "observations": thaw(self._observations_json), "obligation": obligation}
        result = self._check_obligation(compiled, obligation)
        return result, {"schema": PROOF_SCHEMA, "kind": SIGNED_KIND, "engine": ENGINE,
                        "proof": certificate, "result": thaw(freeze(result))}

    def check(self, target, envelope):
        """Check another obligation, including exact membership in this checked context."""
        try:
            compiled = self._prepare(target)
            envelope = thaw(freeze(envelope))
            proof = shape(envelope)
            # Exact snapshot comparison, not a trusted caller receipt/cache hit.
            require(freeze(proof["observations"]) == self._observations_json,
                    "proof uses a different or damaged source dependency; load it separately")
            require(digest(proof["binding"]) == digest(binding(compiled, thaw(self._receipt_json))),
                    "source/interface/target binding")
            result = self._check_obligation(compiled, proof["obligation"])
            require(freeze(envelope["result"]) == freeze(result), "saved result differs from replay")
            return result
        except Exception as exc:
            raise InvalidProof(str(exc)) from exc

    def explain(self, target, envelope):
        result = self.check(target, envelope)
        # All material below belongs to the validated immutable source dependency.
        source_model = thaw(self._observations_json)["source_model"]
        return {"result": result, "route": "checked context; new target obligation, no source reconstruction",
                "interface": {"identity": thaw(self._receipt_json)["identity"],
                    "reductions": source_model["reduction"]["steps"],
                    "erasures": [{"from": e["state"], "symbol": e["symbol"], "to": e["next"], **e["proof"]}
                                 for e in source_model["edges"] if e["proof"]["retired_equalities"]
                                 or e["proof"]["dropped"]["nodes"]]},
                "obligation": thaw(freeze(result["inner"]["target"]))}

    def prove_many(self, targets, *, limits=None):
        targets = thaw(freeze(targets))
        require(type(targets) is list and 0 < len(targets) <= MAX_TARGETS, "1..64 independent targets")
        for target in targets: self._prepare(target)
        target_limits(limits)
        return [self.prove(target, limits=limits) for target in targets]

    def export_source_proof(self):
        return thaw(self._observations_json)

    def describe(self):
        return {"schema": CONTEXT_SCHEMA, "kind": "inspection-only-not-a-certificate",
                "runtime": thaw(self._receipt_json), "target_checked": False, "lean_checked": False,
                "shared_check": "source, reduction, coverage, observations and atomic rows checked at load",
                "original_ir_retained_for_witnesses": True,
                "immutable_dependency_bytes": len(self._observations_json.encode()),
                "mutable_source_models_retained": 0}

    def value(self, raw, width):
        return self._runner.value(raw, width)

    def start(self):
        return self._runner.start()


def load(source, selection, observation_certificate):
    """One full unchanged PR35 source/coverage/atomic check; never trust a receipt."""
    from research.signed_coverage.runtime import load as load_covered
    source = source_text(source)
    selection_json, observation_json = freeze(selection), freeze(observation_certificate)
    selection, observation = thaw(selection_json), thaw(observation_json)
    runner, receipt = load_covered(source, selection, observation)
    # That loader checks this original_ir against a new parse of the source.
    ir_json = freeze(observation["source_model"]["reduction"]["original_ir"])
    return CheckedContext(_KEY, runner=runner, selection=selection_json, observations=observation_json,
                          ir=ir_json, receipt=freeze(receipt))


def build(source, selection, *, limits=None):
    """Source discovery still uses PR35, including its internal checks. Not free work."""
    from research.signed_coverage.producer import infer
    source = source_text(source)
    selection = thaw(freeze(selection))
    options = full_budgets(limits)
    proof, outcome = infer(source, selection, **{k: v for k, v in options.items()
                                               if k not in {"max_target_states", "max_witness_bits"}})
    if proof is None: return None, outcome
    context = load(source, selection, proof)
    return context, context.describe()


def check(source, target, envelope):
    """Fresh standalone replay: re-establish the full dependency, then the target."""
    try:
        target, envelope = thaw(freeze(target)), thaw(freeze(envelope))
        _, selection = prepare(target)
        proof = shape(envelope)
        return load(source, selection, proof["observations"]).check(target, envelope)
    except Exception as exc:
        raise InvalidProof(str(exc)) from exc
