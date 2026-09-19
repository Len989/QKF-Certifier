"""Producer-free target replay over the inferred signed source quotient."""
from research.observations.model import integer, require
from research.signed_predicates.frontend import target_value
from research.signed_predicates.semantics import evaluate
from .adapters import quotient_cells
from .v2_target_checker import check_target_proof as check_v2_target

MAX_PRODUCT = 8192
MAX_WITNESS = 4096


class SignedTarget:
    def __init__(self, system, selected):
        require(system.family == "signed-terminal-predicate", "signed inference target family")
        self.system = system
        self.spec = system.target_data["spec"]
        self.limit = system.target_data["limit"]
        self.blocks, block_of, cells = quotient_cells(system, selected)
        self.table = {(r["state"], r["symbol"]): r["next"] for r in cells}
        self.initial = (block_of[system.initial], 0, 0)
        self.alphabet = ("0", "1")

    def transition(self, state, symbol):
        require(type(symbol) is str and symbol in self.alphabet, "signed target column")
        bit = int(symbol)
        return self.table[state[0], symbol], min(self.limit, state[1] + bit), bit

    def bad(self, state):
        actual = self.system.terminal(self.blocks[state[0]][0]) == "true"
        return actual != target_value(self.spec["target"], state[1], state[2])

    def valid_state(self, raw):
        return (type(raw) is list and len(raw) == 3
                and integer(raw[0], 0, len(self.blocks) - 1)
                and integer(raw[1], 0, self.limit) and integer(raw[2], 0, 1))

    def witness(self, word):
        require(type(word) is list and 0 < len(word) <= MAX_WITNESS
                and all(type(c) is str and c in self.alphabet for c in word),
                "bounded nonempty signed target witness")
        state = self.initial
        for column in word:
            state = self.transition(state, column)
        require(self.bad(state), "signed target witness must refute at its final width")
        width = len(word)
        x = sum(int(bit) << i for i, bit in enumerate(word))
        actual = evaluate(self.system.ir, x, width)
        expected = target_value(self.spec["target"], x.bit_count(), int(word[-1]))
        require(actual == (self.system.terminal(self.blocks[state[0]][0]) == "true")
                and actual != expected, "signed witness whole-word/source-factor agreement")
        native_width = 32 if self.spec["word_type"] == "int" else 64
        mask = (1 << native_width) - 1
        # These are checked finite candidates, not an assumed width-lifting theorem.
        candidates = list(dict.fromkeys((x & mask, 0, 1, 1 << (native_width - 1),
                                        (1 << (native_width - 1)) - 1, mask)))
        native = []
        for value in candidates:
            y = evaluate(self.system.ir, value, native_width)
            e = target_value(self.spec["target"], value.bit_count(), value >> (native_width - 1))
            if y != e:
                native.append({"input": value, "output": y, "expected": e})
        return {"target_status": "refuted", "all_positive_widths": False,
                "witness_width": width, "input": x, "output": actual, "expected": expected,
                "java_width": native_width, "native_width_witnesses": native,
                "native_validation": "whole-word IR evaluation, not Java execution"}


def check_target_proof(system, selected, proof):
    if system.family != "signed-terminal-predicate":
        result = check_v2_target(system, selected, proof)
        return {**result, "all_positive_widths": result["target_status"] == "certified"}
    monitor = SignedTarget(system, selected)
    require(type(proof) is dict and proof.get("kind") in {"closure", "counterexample"},
            "v3 signed target proof kind")
    if proof["kind"] == "counterexample":
        require(set(proof) == {"kind", "word"}, "v3 signed witness fields")
        return monitor.witness(proof["word"])
    require(set(proof) == {"kind", "states"}, "v3 signed closure fields")
    records = proof["states"]
    require(type(records) is list and 0 < len(records) <= MAX_PRODUCT,
            "v3 signed product state budget")
    states, seen = [], set()
    for i, row in enumerate(records):
        require(type(row) is dict and set(row) == {"state", "parent"}
                and monitor.valid_state(row["state"]), "typed v3 signed product record")
        state, parent = tuple(row["state"]), row["parent"]
        require(state not in seen, "distinct v3 signed product states")
        if i == 0:
            require(parent is None and state == monitor.initial, "v3 signed product initial")
        else:
            require(type(parent) is list and len(parent) == 2 and integer(parent[0], 0, i - 1),
                    "earlier v3 signed product parent")
            require(monitor.transition(states[parent[0]], parent[1]) == state,
                    "v3 signed product reachability")
        states.append(state)
        seen.add(state)
    # Compare after every edge: this proves every positive width, not width zero.
    for state in states:
        for column in monitor.alphabet:
            following = monitor.transition(state, column)
            require(following in seen, "v3 signed product closure")
            require(not monitor.bad(following), "v3 signed terminal target agreement")
    return {"target_status": "certified", "all_positive_widths": True,
            "target_product_states": len(states), "target_checked_transitions": 2 * len(states),
            "java_width": 32 if monitor.spec["word_type"] == "int" else 64}
