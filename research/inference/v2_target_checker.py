"""Direct target replay for inference v2, including ascending successor.

The ascending monitor is the already accepted generic target_rules semantics.
Only the source-side runner is replaced by the inferred quotient.
"""
from research.observations.model import integer, require
from research.observations.target_rules import (
    COLUMN_NAMES, advance as target_advance, columns as target_columns,
    compile_spec, concrete_violation, initial as target_initial,
    valid_state as target_state_valid, violation as target_violation,
)
from research.inference.adapters import quotient_cells
from research.inference.target_checker import check_target_proof as check_v1_target


def _table(cells):
    return {(r["state"], r["symbol"]): (r["output"], r["next"]) for r in cells}


class AscendingTarget:
    def __init__(self, system, selected):
        require(system.family == "ascending-region", "ascending inference family")
        self.system = system
        self.spec = system.target_data["spec"]
        self.program = compile_spec(self.spec)
        require(self.spec["profile"] == "ascending", "ascending typed target")
        self.blocks, self.block_of, cells = quotient_cells(system, selected)
        self.table = _table(cells)
        self.alphabet = target_columns("ascending")
        self.names = COLUMN_NAMES["ascending"]
        require({column[:3] for column in self.alphabet} == set(system.alphabet),
                "complete inferred ascending source projection")
        self.initial = (self.block_of[system.initial], False, *target_initial(self.program))

    def transition(self, state, column):
        require(type(column) is str and column in self.alphabet, "legal ascending target column")
        env = dict(zip(self.names, map(int, column)))
        q, nonempty, *monitor = state
        output, following = self.table[q, column[:3]]
        env["output"] = int(output)
        return (following, True, *target_advance(self.program, monitor, env)), env, output

    def bad(self, state):
        if not state[1]:
            return None
        return target_violation(self.program, state[2:])

    def state_valid(self, raw):
        return (
            type(raw) is list
            and len(raw) == len(self.initial)
            and integer(raw[0], 0, len(self.blocks) - 1)
            and type(raw[1]) is bool
            and target_state_valid(self.program, raw[2:])
        )

    def trace(self, word):
        state = self.initial
        outputs = []
        values = {name: 0 for name in self.names}
        for i, column in enumerate(word):
            state, env, output = self.transition(state, column)
            outputs.append(output)
            for name in self.names:
                values[name] |= env[name] << i
        values["output"] = sum(int(bit) << i for i, bit in enumerate(outputs))
        return state, {"width": len(word), **values}


def check_target_proof(system, selected, proof):
    if system.family != "ascending-region":
        return check_v1_target(system, selected, proof)

    monitor = AscendingTarget(system, selected)
    require(type(proof) is dict and proof.get("kind") in {"closure", "counterexample"},
            "v2 ascending target proof kind")

    if proof["kind"] == "counterexample":
        require(set(proof) == {"kind", "word", "reason", "values"},
                "v2 ascending counterexample fields")
        word = proof["word"]
        require(type(word) is list and 0 < len(word) <= 256
                and all(type(c) is str and c in monitor.alphabet for c in word),
                "bounded ascending target witness")
        state, values = monitor.trace(word)
        reason = monitor.bad(state)
        require(reason is not None and reason == proof["reason"],
                "ascending inferred quotient target violation")
        require(proof["values"] == values, "ascending target witness decoding")
        require(concrete_violation(monitor.spec, values) == reason,
                "independent whole-integer typed successor violation")

        from research.observations.ascending_execution import integer_value
        from research.observations.ascending_source import extract_region

        key = tuple(values[k] for k in ("width", "must", "may", "seed"))
        require(integer_value(extract_region(system.source), key) == values["output"],
                "direct integer ascending source execution")
        return {
            "target_status": "refuted",
            "target_reason": reason,
            "witness_width": len(word),
            "target_checked_by": [
                "inferred source quotient",
                "generic target_rules",
                "integer source execution",
                "integer target formula",
            ],
        }

    require(set(proof) == {"kind", "states"}, "v2 ascending closure fields")
    nodes = proof["states"]
    require(type(nodes) is list and 0 < len(nodes) <= 8192,
            "v2 ascending target state budget")
    states, seen = [], set()
    for i, node in enumerate(nodes):
        require(type(node) is dict and set(node) == {"state", "parent"}
                and monitor.state_valid(node["state"]),
                "typed v2 ascending target state")
        state = tuple(node["state"])
        require(state not in seen, "distinct v2 ascending target states")
        parent = node["parent"]
        if i == 0:
            require(parent is None and state == monitor.initial,
                    "v2 ascending target initial state")
        else:
            require(type(parent) is list and len(parent) == 2
                    and integer(parent[0], 0, i - 1)
                    and type(parent[1]) is str and parent[1] in monitor.alphabet,
                    "v2 ascending target parent")
            following, _env, _output = monitor.transition(states[parent[0]], parent[1])
            require(following == state, "v2 ascending target reachability")
        require(monitor.bad(state) is None, "inferred quotient violates successor target")
        states.append(state)
        seen.add(state)

    for state in states:
        for column in monitor.alphabet:
            following, _env, _output = monitor.transition(state, column)
            require(following in seen, "v2 ascending target closure")

    return {
        "target_status": "certified",
        "target_product_states": len(states),
        "target_checked_transitions": len(states) * len(monitor.alphabet),
        "target_observations": len(monitor.program["atoms"]),
        "target_rules": "coordinatewise-words-and-unsigned-order-v1",
    }
