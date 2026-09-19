"""Richer source-derived candidate library for observation inference v2.

V1 certificates remain untouched.  This adapter reuses their accepted source
residual semantics and derives a new finite library containing Boolean tests,
integer order cuts, integer equalities, and pairwise residual relations.
"""
import hashlib

from research.observations.model import digest, require
from research.inference.adapters import System as V1System

LIBRARY = "residual-projections-v2"
MAX_FEATURES = 256


class System:
    def __init__(self, source, target):
        base = V1System(source, target)
        self.base = base
        for name in (
            "source", "target", "compiled", "kind", "family", "ir", "initial",
            "alphabet", "slot_labels", "target_data", "states", "index"
        ):
            setattr(self, name, getattr(base, name))
        self.features = self._features()
        self.feature_by_id = {row["id"]: row for row in self.features}
        self.binding = {
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "target_sha256": digest(target),
            "specification_sha256": self.compiled["specification_sha256"],
            "family": self.family,
            "source_ir_sha256": digest(self.ir),
            "candidate_library": LIBRARY,
            "candidate_library_sha256": digest(self.features),
        }

    def step(self, state, symbol):
        return self.base.step(state, symbol)

    def terminal(self, state):
        return self.base.terminal(state)

    def _features(self):
        require(all(len(s) == len(self.slot_labels) for s in self.states),
                "typed residual width")
        rows = []
        integer_slots = []

        # Prefer broad order cuts before singleton equalities.  Boolean
        # coordinates need only one side because the other is its complement.
        for slot, label in enumerate(self.slot_labels):
            values = []
            for state in self.states:
                value = state[slot]
                require(type(value) in {int, bool}, "typed residual coordinate")
                if not any(type(value) is type(old) and value == old for old in values):
                    values.append(value)
            if len(values) <= 1:
                continue

            if all(type(v) is bool for v in values):
                rows.append({
                    "id": "slot" + str(slot) + ":false",
                    "kind": "bool_false",
                    "slot": slot,
                    "label": label + " == False",
                })
                continue

            require(all(type(v) is int for v in values), "homogeneous integer residual coordinate")
            integer_slots.append(slot)
            values.sort()
            for cut in values[:-1]:
                rows.append({
                    "id": "slot" + str(slot) + "<=" + str(cut),
                    "kind": "le",
                    "slot": slot,
                    "cut": cut,
                    "label": label + " <= " + str(cut),
                })
            for value in values:
                rows.append({
                    "id": "slot" + str(slot) + "==" + str(value),
                    "kind": "eq",
                    "slot": slot,
                    "value": value,
                    "label": label + " == " + str(value),
                })

        # Relations can express a useful invariant without naming either
        # concrete residual value.  Keep only nonconstant questions.
        for p, left in enumerate(integer_slots):
            for right in integer_slots[p + 1:]:
                for kind, op, label_op in (
                    ("slot_le", lambda a, b: a <= b, " <= "),
                    ("slot_eq", lambda a, b: a == b, " == "),
                ):
                    answers = [op(state[left], state[right]) for state in self.states]
                    if len(set(answers)) <= 1:
                        continue
                    rows.append({
                        "id": "slot" + str(left) + (":le:" if kind == "slot_le" else ":eq:") + str(right),
                        "kind": kind,
                        "left": left,
                        "right": right,
                        "label": self.slot_labels[left] + label_op + self.slot_labels[right],
                    })

        require(len(rows) <= MAX_FEATURES, "v2 candidate observation library budget")
        return rows

    def feature_value(self, feature_id, state):
        feature = self.feature_by_id[feature_id]
        kind = feature["kind"]
        if kind == "bool_false":
            return state[feature["slot"]] is False
        if kind == "le":
            return state[feature["slot"]] <= feature["cut"]
        if kind == "eq":
            return state[feature["slot"]] == feature["value"]
        if kind == "slot_le":
            return state[feature["left"]] <= state[feature["right"]]
        if kind == "slot_eq":
            return state[feature["left"]] == state[feature["right"]]
        raise ValueError("unknown v2 observation feature")
