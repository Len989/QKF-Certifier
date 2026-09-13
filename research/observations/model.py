"""Explicit finite native semantics; no observation partition is supplied."""
import hashlib
import json

MODEL_SCHEMA = "qkf-finite-observation-model-v1"
CERT_SCHEMA = "qkf-derived-observation-v1"
ATOMIC_CERT_SCHEMA = "qkf-derived-observation-atomic-v1"
MAX_STATES = 64
MAX_CLASSES = 8  # Complete powerset rows are deliberately bounded.
MAX_ATOMIC_CLASSES = MAX_STATES  # No enumeration of the powerset in this encoding.


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode()).hexdigest()


def integer(value, lower, upper):
    return type(value) is int and lower <= value <= upper


def names(value, limit):
    require(type(value) is list and 0 < len(value) <= limit, "finite nonempty names")
    require(all(type(x) is str and x for x in value), "string names")
    require(len(value) == len(set(value)), "distinct names")
    return sorted(value)


class Model:
    def __init__(self, data):
        require(type(data) is dict and set(data) == {
            "schema", "states", "alphabet", "outputs", "initial", "terminal", "steps", "binding"
        }, "model fields")
        require(data["schema"] == MODEL_SCHEMA, "model schema")
        self.states = names(data["states"], MAX_STATES)
        self.alphabet = names(data["alphabet"], 32)
        self.outputs = names(data["outputs"], 16)
        require(type(data["initial"]) is str and data["initial"] in self.states, "initial state")
        self.initial = data["initial"]
        require(type(data["terminal"]) is dict and set(data["terminal"]) == set(self.states),
                "terminal observations cover the carrier")
        require(all(type(v) is str for v in data["terminal"].values()), "terminal labels")
        self.terminal = dict(data["terminal"])
        require(type(data["binding"]) is dict, "native binding")
        self.binding = data["binding"]
        rows = data["steps"]
        require(type(rows) is list and len(rows) == len(self.states) * len(self.alphabet),
                "complete native table")
        self.step = {}
        for row in rows:
            require(type(row) is dict and set(row) == {"state", "symbol", "output", "next"},
                    "native cell fields")
            require(all(type(x) is str for x in row.values()), "native cell names")
            s, a, y, t = (row[k] for k in ("state", "symbol", "output", "next"))
            require(s in self.states and a in self.alphabet and t in self.states
                    and y in self.outputs, "native cell types")
            require((s, a) not in self.step, "duplicate native cell")
            self.step[s, a] = (y, t)
        self.index = {s: i for i, s in enumerate(self.states)}
        self.data = {"schema": MODEL_SCHEMA, "states": self.states, "alphabet": self.alphabet,
                     "outputs": self.outputs, "initial": self.initial, "terminal": self.terminal,
                     "binding": self.binding, "steps": [
                         {"state": s, "symbol": a, "output": self.step[s, a][0],
                          "next": self.step[s, a][1]}
                         for s in self.states for a in self.alphabet]}
        self.sha256 = digest(self.data)

    def mask(self, predicate):
        return sum(1 << i for i, s in enumerate(self.states) if predicate(s))

    def run(self, state, word):
        labels = []
        for a in word:
            y, state = self.step[state, a]
            labels.append(y)
        return labels, state
