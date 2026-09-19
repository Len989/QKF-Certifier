"""Source-derived residual systems and candidate observation libraries.

The library is deliberately finite and typed.  It contains equality questions
about semantic residual coordinates (arithmetic carries/tails, accumulated
predicate mismatches, Boolean control registers, and ascending offsets).  No
method name selects a hand-written state machine.
"""
import hashlib

from research.observations.model import digest, require
from research.unified.schema import compile_target

MAX_NATIVE_STATES = 512


def _value_id(value):
    if type(value) is bool:
        return "b1" if value else "b0"
    require(type(value) is int, "integer or Boolean residual feature")
    return "i" + str(value)


class System:
    def __init__(self, source, target):
        self.source = source
        self.target = target
        self.compiled = compile_target(target)
        self.kind = self.compiled["kind"]
        self.family = None
        self.ir = None
        self.initial = None
        self.alphabet = None
        self._step = None
        self._terminal = None
        self.slot_labels = []
        self.target_data = None

        if self.kind == "word_result":
            from research.wordexpr.frontend import goal, read_source
            from research.wordexpr import semantics as sem

            spec = self.compiled["specification"]
            ir = read_source(source, spec["entry"])
            target_ir = goal(spec)
            self.family = "streaming-word"
            self.ir = ir
            self.initial = sem.initial(ir)
            self.alphabet = ("0", "1")
            self._step = lambda state, symbol: sem.cell(ir, state, symbol)
            self._terminal = lambda _state: "_"
            self.slot_labels = [
                "node[" + str(i) + "]:" + str(node[0]) + ":residual"
                for i, node in enumerate(ir["nodes"])
            ]
            self.target_data = {"ir": target_ir, "spec": spec}

        elif self.kind == "boolean_predicate":
            from research.wordexpr.predicate_frontend import goal, read_source
            from research.wordexpr import predicate_semantics as sem

            spec = self.compiled["specification"]
            ir = read_source(source, spec["entry"], spec["word_type"])
            limit = goal(spec)
            self.family = "terminal-predicate"
            self.ir = ir
            self.initial = sem.initial(ir)
            self.alphabet = ("0", "1")
            self._step = lambda state, symbol: ("_", sem.cell(ir, state, symbol))
            self._terminal = lambda state: str(bool(sem.terminal(ir, state))).lower()
            n = len(ir["nodes"])
            self.slot_labels = [
                "node[" + str(i) + "]:" + str(node[0]) + ":residual"
                for i, node in enumerate(ir["nodes"])
            ] + [
                "atom[" + str(i) + "]:mismatch_seen"
                for i in range(len(ir["atoms"]))
            ]
            self.target_data = {"limit": limit, "spec": spec, "node_count": n}

        elif self.kind == "successor":
            require(self.compiled["profile"] == "ascending", "ascending successor inference profile")
            from research.observations.ascending_kernel import ALPHABET, cell
            from research.observations.ascending_source import read_source

            ir = read_source(source)
            self.family = "ascending-region"
            self.ir = ir
            self.initial = tuple(ir["register_initial"]) + (0,)
            self.alphabet = tuple(ALPHABET)
            self._step = lambda state, symbol: cell(ir, state, symbol)
            self._terminal = lambda _state: "unobserved"
            self.slot_labels = [
                "register[" + str(i) + "]"
                for i in range(len(ir["register_initial"]))
            ] + ["offset"]
            self.target_data = {"spec": self.compiled["specification"]}
        else:
            raise ValueError("observation-inference-v1 does not yet support target kind: " + self.kind)

        self.states = self._reachable()
        self.index = {state: i for i, state in enumerate(self.states)}
        self.features = self._features()
        self.feature_by_id = {f["id"]: f for f in self.features}
        self.binding = {
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "target_sha256": digest(target),
            "specification_sha256": self.compiled["specification_sha256"],
            "family": self.family,
            "source_ir_sha256": digest(self.ir),
            "candidate_library_sha256": digest(self.features),
        }

    def step(self, state, symbol):
        require(state in self.index and symbol in self.alphabet, "known inference transition")
        output, following = self._step(state, symbol)
        require(type(output) is str and following in self.index, "closed source residual transition")
        return output, following

    def terminal(self, state):
        require(state in self.index, "known inference terminal state")
        value = self._terminal(state)
        require(type(value) is str, "string terminal observation")
        return value

    def _reachable(self):
        states = [self.initial]
        seen = {self.initial}
        for state in states:
            for symbol in self.alphabet:
                _, following = self._step(state, symbol)
                require(type(following) is tuple, "tuple residual state")
                if following not in seen:
                    require(len(states) < MAX_NATIVE_STATES, "inference native-state budget")
                    seen.add(following)
                    states.append(following)
        return states

    def _features(self):
        require(all(len(s) == len(self.slot_labels) for s in self.states), "typed residual width")
        features = []
        for slot, label in enumerate(self.slot_labels):
            values = []
            for state in self.states:
                value = state[slot]
                require(type(value) in {int, bool}, "typed residual coordinate")
                if not any(type(value) is type(old) and value == old for old in values):
                    values.append(value)
            values.sort(key=lambda x: (type(x) is not bool, int(x)))
            if len(values) <= 1:
                continue
            for value in values:
                features.append({
                    "id": "slot" + str(slot) + "=" + _value_id(value),
                    "slot": slot,
                    "value": value,
                    "label": label + " == " + repr(value),
                })
        require(len(features) <= 128, "candidate observation library budget")
        return features

    def feature_value(self, feature_id, state):
        feature = self.feature_by_id[feature_id]
        return type(state[feature["slot"]]) is type(feature["value"]) and state[feature["slot"]] == feature["value"]


def blocks_for(system, selected):
    require(type(selected) is list and len(selected) == len(set(selected)), "distinct selected observations")
    require(all(x in system.feature_by_id for x in selected), "selected observation belongs to library")
    groups = {}
    for state in system.states:
        key = tuple(system.feature_value(fid, state) for fid in selected)
        groups.setdefault(key, []).append(state)
    blocks = list(groups.values())
    blocks.sort(key=lambda block: min(system.index[s] for s in block))
    block_of = {state: i for i, block in enumerate(blocks) for state in block}
    return blocks, block_of


def conflict(system, selected):
    """Return the first behavioral/stability conflict in the induced quotient."""
    blocks, block_of = blocks_for(system, selected)
    for block_index, block in enumerate(blocks):
        for i, left in enumerate(block):
            for right in block[i + 1:]:
                lt, rt = system.terminal(left), system.terminal(right)
                if lt != rt:
                    return {
                        "reason": "terminal",
                        "block": block_index,
                        "left": list(left),
                        "right": list(right),
                        "left_value": lt,
                        "right_value": rt,
                    }
                for symbol in system.alphabet:
                    ly, ln = system.step(left, symbol)
                    ry, rn = system.step(right, symbol)
                    if ly != ry:
                        return {
                            "reason": "output",
                            "block": block_index,
                            "symbol": symbol,
                            "left": list(left),
                            "right": list(right),
                            "left_value": ly,
                            "right_value": ry,
                        }
                    if block_of[ln] != block_of[rn]:
                        return {
                            "reason": "continuation",
                            "block": block_index,
                            "symbol": symbol,
                            "left": list(left),
                            "right": list(right),
                            "left_next": list(ln),
                            "right_next": list(rn),
                            "left_next_block": block_of[ln],
                            "right_next_block": block_of[rn],
                        }
    return None


def quotient_cells(system, selected):
    blocks, block_of = blocks_for(system, selected)
    cells = []
    for i, block in enumerate(blocks):
        representative = block[0]
        for symbol in system.alphabet:
            output, following = system.step(representative, symbol)
            cells.append({
                "state": i,
                "symbol": symbol,
                "output": output,
                "next": block_of[following],
            })
    return blocks, block_of, cells
