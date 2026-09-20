"""Immutable finite-union row actions, with no source or certificate imports.

These constructors check finite structure, NOT correspondence to external code.
Use signed_runtime.runtime.load for source-bound execution. A row contains the
preimages of singleton destination classes. It does not contain a forward table.
"""
from dataclasses import dataclass


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, low, high):
    return type(value) is int and low <= value <= high


@dataclass(frozen=True, slots=True)
class AtomicRow:
    atoms: tuple[int, ...]

    def __post_init__(self):
        require(type(self.atoms) is tuple and 1 <= len(self.atoms) <= 64,
                "immutable row of 1..64 atoms")
        top, seen = (1 << len(self.atoms)) - 1, 0
        for image in self.atoms:
            require(integer(image, 0, top) and not image & seen,
                    "typed, bounded and pairwise-disjoint atom images")
            seen |= image

    @property
    def guard(self):
        result = 0
        for image in self.atoms:
            result |= image
        return result

    @property
    def kernel_projection(self):
        return sum(1 << j for j, image in enumerate(self.atoms) if image)

    def image(self, subset):
        """h(P) = union of the supplied singleton images; h(empty) = empty."""
        require(integer(subset, 0, (1 << len(self.atoms)) - 1), "row subset")
        result = 0
        for j, image in enumerate(self.atoms):
            if subset & (1 << j):
                result |= image
        return result

    def same_image(self, left, right):
        top = (1 << len(self.atoms)) - 1
        require(integer(left, 0, top) and integer(right, 0, top), "row kernel arguments")
        projection = self.kernel_projection
        return left & projection == right & projection


@dataclass(frozen=True, slots=True)
class Machine:
    alphabet: tuple[str, ...]
    outputs: tuple[str, ...]
    terminal: tuple[str, ...]
    initial: int
    # rows[symbol index][output index], each indexed by destination class.
    rows: tuple[tuple[AtomicRow, ...], ...]

    def __post_init__(self):
        for values, limit in ((self.alphabet, 32), (self.outputs, 16)):
            require(type(values) is tuple and 0 < len(values) <= limit
                    and all(type(x) is str and x for x in values)
                    and len(set(values)) == len(values), "immutable distinct action labels")
        require(type(self.terminal) is tuple and 0 < len(self.terminal) <= 64
                and all(type(x) is str for x in self.terminal), "immutable terminal labels")
        require(integer(self.initial, 0, self.classes - 1), "initial class")
        require(type(self.rows) is tuple and len(self.rows) == len(self.alphabet), "row symbols")
        top = (1 << self.classes) - 1
        for family in self.rows:
            require(type(family) is tuple and len(family) == len(self.outputs), "row outputs")
            covered = 0
            for row in family:
                require(type(row) is AtomicRow and len(row.atoms) == self.classes,
                        "row carrier must match machine")
                require(not covered & row.guard, "overlapping output guards")
                covered |= row.guard
            require(covered == top, "rows must cover every source class exactly once")

    @property
    def classes(self):
        return len(self.terminal)

    def row(self, symbol, output):
        require(type(symbol) is str and symbol in self.alphabet, "unknown input symbol")
        require(type(output) is str and output in self.outputs, "unknown output label")
        return self.rows[self.alphabet.index(symbol)][self.outputs.index(output)]

    def step(self, state, symbol):
        """Recover the unique (output, destination) from atomic preimages only."""
        require(integer(state, 0, self.classes - 1), "runtime source class")
        require(type(symbol) is str and symbol in self.alphabet, "unknown input symbol")
        bit = 1 << state
        for output, row in zip(self.outputs, self.rows[self.alphabet.index(symbol)]):
            for destination, image in enumerate(row.atoms):
                if image & bit:
                    return output, destination
        # Constructor proves this unreachable; do not replace failure with a value.
        raise RuntimeError("checked atomic action lost coverage")

    def snapshot(self):
        """Detached inspection data, not a source certificate or a loading API."""
        return {"alphabet": list(self.alphabet), "outputs": list(self.outputs),
                "terminal": list(self.terminal), "initial": self.initial,
                "rows": [{"symbol": a, "output": y, "atoms": list(row.atoms),
                          "guard": row.guard, "kernel_projection": row.kernel_projection}
                         for a, family in zip(self.alphabet, self.rows)
                         for y, row in zip(self.outputs, family)]}
