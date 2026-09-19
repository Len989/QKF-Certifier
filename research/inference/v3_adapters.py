"""Source-derived terminal and residual questions for signed inference v3.

No source names, target formulas or external-corpus identities choose features.
The full source terminal output is a candidate, not a hand-written automaton.
"""
import hashlib
from itertools import product

from research.observations.model import digest, require
from research.signed_predicates import semantics as signed
from research.signed_predicates.frontend import goal, read_source
from research.unified.v3_schema import SIGNED_KIND, compile_target
from .adapters import System as V1System
from .v2_adapters import MAX_FEATURES, System as V2System

LIBRARY = "terminal-and-residual-projections-v3"
MAX_TERMINAL_LOOKAHEAD = 2


class CapacityExceeded(ValueError):
    """A finite source/candidate budget was reached, not a negative verdict."""


class SignedSource(V1System):
    def __init__(self, source, target):
        self.source, self.target = source, target
        self.compiled = compile_target(target)
        self.kind = self.compiled["kind"]
        require(self.kind == SIGNED_KIND, "signed source target kind")
        spec = self.compiled["specification"]
        self.ir = read_source(source, spec["entry"], spec["word_type"])
        self.family = "signed-terminal-predicate"
        self.initial = signed.initial(self.ir)
        self.alphabet = ("0", "1")
        self._step = lambda state, symbol: ("_", signed.cell(self.ir, state, symbol))
        self._terminal = lambda state: str(bool(signed.terminal(self.ir, state))).lower()
        self.slot_labels = [
            "node[" + str(i) + "]:" + node[0] + ":residual"
            for i, node in enumerate(self.ir["nodes"])
        ]
        for i, atom in enumerate(self.ir["atoms"]):
            names = (("mismatch_seen", "unused") if atom["kind"] == "eq"
                     else ("nonzero_seen", "last_bit"))
            self.slot_labels.extend("atom[" + str(i) + "]:" + name for name in names)
        self.target_data = {"spec": spec, "limit": goal(spec)}
        self.states = self._reachable()
        self.index = {state: i for i, state in enumerate(self.states)}


class System(V2System):
    def __init__(self, source, target):
        require(type(source) is str, "v3 source text")
        compiled = compile_target(target)
        try:
            base = (SignedSource(source, target) if compiled["kind"] == SIGNED_KIND
                    else V2System(source, target))
            self.base = base
            for name in ("source", "target", "compiled", "kind", "family", "ir",
                         "initial", "alphabet", "slot_labels", "target_data", "states", "index"):
                setattr(self, name, getattr(base, name))
            features = self._features()
        except ValueError as exc:
            if str(exc) in {"inference native-state budget", "v2 candidate observation library budget"}:
                raise CapacityExceeded(str(exc)) from exc
            raise
        # Bounded source-output continuations, generated without consulting
        # the goal.  Equivalent questions on the reachable carrier are deduped.
        if self.family == "signed-terminal-predicate":
            terminal_features, seen = [], set()
            for length in range(MAX_TERMINAL_LOOKAHEAD + 1):
                for bits in product(self.alphabet, repeat=length):
                    suffix = "".join(bits)
                    answers = tuple(self._after(state, suffix) for state in self.states)
                    if len(set(answers)) <= 1 or answers in seen:
                        continue
                    seen.add(answers)
                    terminal_features.append({
                        "id": "terminal_after:" + suffix,
                        "kind": "terminal_after", "suffix": suffix,
                        "label": "source terminal after LSB suffix " + repr(suffix) + " == True",
                    })
            features = terminal_features + features
        if len(features) > MAX_FEATURES:
            raise CapacityExceeded("v3 candidate observation library budget")
        self.features = features
        self.feature_by_id = {row["id"]: row for row in features}
        self.binding = {
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "target_sha256": digest(target),
            "specification_sha256": self.compiled["specification_sha256"],
            "family": self.family, "source_ir_sha256": digest(self.ir),
            "candidate_library": LIBRARY, "candidate_library_sha256": digest(features),
        }

    def _after(self, state, suffix):
        for symbol in suffix:
            _, state = self.step(state, symbol)
        return self.terminal(state) == "true"

    def feature_value(self, feature_id, state):
        feature = self.feature_by_id[feature_id]
        if feature["kind"] == "terminal_after":
            return self._after(state, feature["suffix"])
        return super().feature_value(feature_id, state)
