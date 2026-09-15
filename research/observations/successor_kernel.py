"""Replay an ascending source factor against a separately supplied successor goal.

A positive package is a finite closed joint observation, not a width sample.
A negative package is checked through the factor, whole-integer source AST and
independent integer target. Neither replay imports a producer or native harness.
"""
import hashlib

from .ascending_execution import integer_value
from .ascending_kernel import ALPHABET, Runner
from .ascending_source import extract_region
from .model import digest, integer, require
from .successor_spec import (INITIAL, RULES, check_spec, columns,
                             concrete_violation, decode, step, violation)

SCHEMA = "qkf-masked-successor-property-v1"
MAX_STATES = 8192
MAX_WITNESS = 256


class System:
    def __init__(self, source, source_certificate, spec):
        self.claim = check_spec(spec)
        self.runner = Runner(source, source_certificate)
        self.classes = len(source_certificate["observations"]["blocks"])
        self.alphabet = columns()
        require({c[:3] for c in self.alphabet} == set(ALPHABET),
                "complete independent successor input projection")
        self.initial = (self.runner.initial, *INITIAL)
        self.binding = {
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "source_certificate_sha256": digest(source_certificate),
            "specification_sha256": digest(spec),
            "target_rules": RULES,
        }

    def advance(self, state, column):
        output, following = self.runner.cells[state[0], column[:3]]
        return (following, *step(state[1:], column, int(output)))

    def bad(self, state):
        return violation(self.claim, state[1:])

    def state_valid(self, state):
        return (type(state) is list and len(state) == 7
                and integer(state[0], 0, self.classes - 1)
                and all(type(x) is bool for x in state[1:4])
                and all(integer(x, -1, 1) for x in state[4:]))

    def trace(self, word):
        state = self.initial
        outputs = []
        for column in word:
            outputs.append(self.runner.cells[state[0], column[:3]][0])
            state = self.advance(state, column)
        return state, outputs


def _scope(spec, universal):
    return {
        "claim": "masked_" + spec["claim"],
        "specification_sha256": digest(spec),
        "preconditions": spec["preconditions"],
        "all_positive_payload_widths": universal,
        "semantics": "restricted unsigned mathematical source region; emitted payload only",
        "trusted_frontend_and_slice_rules": True,
        "whole_helper": False,
        "native_java_all_widths": False,
        "new_lean_theorem": False,
    }


def check(source, source_certificate, spec, certificate):
    system = System(source, source_certificate, spec)
    require(type(certificate) is dict and certificate.get("schema") == SCHEMA
            and certificate.get("kind") in {"closed_observation", "counterexample"},
            "successor property certificate kind")
    require(digest(certificate.get("binding")) == digest(system.binding),
            "successor source, factor and independent target binding")
    if certificate["kind"] == "counterexample":
        require(set(certificate) == {"schema", "kind", "binding", "word", "values", "reason"},
                "successor counterexample fields")
        word = certificate["word"]
        require(type(word) is list and 0 < len(word) <= MAX_WITNESS
                and all(type(c) is str and c in system.alphabet for c in word),
                "bounded legal successor witness columns")
        state, outputs = system.trace(word)
        reason = system.bad(state)
        require(reason is not None and reason == certificate["reason"],
                "successor witness must violate the protected target")
        values = decode(word, outputs)
        require(digest(certificate["values"]) == digest(values), "successor concrete decoding")
        require(concrete_violation(spec, values) == reason, "independent integer successor violation")
        key = tuple(values[k] for k in ("width", "must", "may", "seed"))
        require(integer_value(extract_region(source), key) == values["output"],
                "successor witness direct integer source execution")
        return {"status": "refuted", **_scope(spec, False), "reason": reason,
                "counterexample": values, "witness_width": len(word),
                "checked_by": ["source factor", "integer source execution", "integer target"]}

    require(set(certificate) == {"schema", "kind", "binding", "states"},
            "closed successor observation fields")
    nodes = certificate["states"]
    require(type(nodes) is list and 0 < len(nodes) <= MAX_STATES, "successor state budget")
    states = []
    seen = set()
    for i, node in enumerate(nodes):
        require(type(node) is dict and set(node) == {"state", "parent"}
                and system.state_valid(node["state"]), "typed successor joint observation")
        state = tuple(node["state"])
        require(state not in seen, "distinct successor joint observations")
        parent = node["parent"]
        if i == 0:
            require(parent is None and state == system.initial, "successor initial observation")
        else:
            require(type(parent) is list and len(parent) == 2
                    and integer(parent[0], 0, i - 1)
                    and type(parent[1]) is str and parent[1] in system.alphabet,
                    "earlier successor observation parent")
            require(system.advance(states[parent[0]], parent[1]) == state,
                    "successor reachability equation")
        require(system.bad(state) is None, "a protected successor target obligation fails")
        states.append(state)
        seen.add(state)
    for state in states:
        for column in system.alphabet:
            require(system.advance(state, column) in seen,
                    "successor observation must be closed under every legal column")
    return {"status": "certified", **_scope(spec, True),
            "closed_states": len(states), "checked_transitions": len(states) * len(system.alphabet),
            "alphabet_columns": len(system.alphabet), "source_factor_classes": system.classes,
            "obligations": spec["obligations"], "native_validation": "separate bounded experiment"}
