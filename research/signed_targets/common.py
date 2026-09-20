"""Finite target monitor; source transitions come ONLY from PR30 atomic rows.

The target grammar and saturation semantics are retained from PR24/v3. The
monitor does not infer a goal, inspect source syntax, or consume forward cells.
Its initial state is not an input word. Obligations apply after every bit.
"""
from research.observations.model import integer, require
from research.signed_bridge.model import COMPLETION, request
from research.signed_predicates.frontend import goal, target_value
from research.unified.v3_schema import SIGNED_KIND, compile_target

SCHEMA = "qkf-signed-row-target-v1"
ENGINE = "signed-observation-row-target-v1"
MAX_PRODUCT = 8192
MAX_WITNESS = 4096
DEFAULTS = {"max_states": 64, "max_observations": 63, "max_pullbacks": 4096,
            "max_classes": 64, "max_target_states": MAX_PRODUCT,
            "max_witness_bits": MAX_WITNESS}


def prepare(target):
    compiled = compile_target(target)
    require(compiled["kind"] == SIGNED_KIND, "row targets require signed_boolean_predicate")
    spec = compiled["specification"]
    return compiled, request(spec["entry"], spec["word_type"])


def budgets(value):
    value = {} if value is None else value
    require(type(value) is dict and set(value) <= set(DEFAULTS), "signed row budget fields")
    result = {**DEFAULTS, **value}
    limits = {"max_states": (1, 64), "max_observations": (0, 63),
              "max_pullbacks": (0, 100000), "max_classes": (1, 64),
              "max_target_states": (1, MAX_PRODUCT), "max_witness_bits": (0, MAX_WITNESS)}
    for name, (low, high) in limits.items():
        require(integer(result[name], low, high), "invalid resource ceiling: " + name)
    return result


def binding(compiled, receipt):
    return {"source_sha256": receipt["identity"]["source_sha256"],
            "request_sha256": receipt["identity"]["request_sha256"],
            "observation_certificate_sha256": receipt["identity"]["certificate_sha256"],
            "action_sha256": receipt["action_sha256"],
            "target_sha256": compiled["target_sha256"],
            "specification_sha256": compiled["specification_sha256"],
            "contract": compiled["specification"]["contract"], "completion": COMPLETION}


class Monitor:
    """Internal monitor: caller must first establish the Runner's source binding."""
    def __init__(self, runner, spec):
        self.runner, self.spec = runner, spec
        self.limit = goal(spec)
        self.initial = (runner.machine.initial, 0, 0)
        self.alphabet = ("0", "1")

    def valid(self, raw):
        return (type(raw) is list and len(raw) == 3
                and integer(raw[0], 0, self.runner.machine.classes - 1)
                and integer(raw[1], 0, self.limit) and integer(raw[2], 0, 1))

    def step(self, state, symbol):
        require(type(symbol) is str and symbol in self.alphabet, "binary target column")
        output, following = self.runner.machine.step(state[0], symbol)
        require(output == "_", "terminal-only source output")
        bit = int(symbol)
        return following, min(self.limit, state[1] + bit), bit

    def actual(self, state):
        label = self.runner.machine.terminal[state[0]]
        require(label in {"true", "false"}, "target obligation requires a positive-width state")
        return label == "true"

    def expected(self, state):
        return target_value(self.spec["target"], state[1], state[2])

    def bad(self, state):
        return self.actual(state) != self.expected(state)


def result(compiled, receipt, checked):
    return {"status": checked["status"], "engine": ENGINE,
            "claim": "source_matches_independent_signed_target",
            "all_positive_widths": checked["status"] == "certified",
            "target_checked": True, "source_interface_verified": True,
            "lean_checked": False, "completion": COMPLETION,
            "target_sha256": compiled["target_sha256"],
            "runtime": receipt, "target": checked,
            "scope": "all positive widths in retained modular profile; trusted restricted frontend, "
                     "residual and target semantics, Python checkers and row runtime; no new Lean theorem"}
