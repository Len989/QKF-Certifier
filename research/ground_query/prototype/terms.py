"""Interned input-DAG nodes for the retained Paper II closure algorithms.

The schema rejects duplicate (symbol, argument-id) nodes and the producer builds
exactly one object for each id. Identity equality therefore IS syntactic equality
within a run. No recursive tuple hashing, printing or tree unfolding is needed.
This adapter is new; the archived nested-tuple implementation is unchanged.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True, eq=False)
class Term:
    head: str
    args: tuple
    ordinal: int
    height: int = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, 'height', 1 + max(a.height for a in self.args) if self.args else 0)

    def pretty(self):
        # A stable input-node label, not a recursively expanded expression.
        return f'{self.head}@{self.ordinal:08d}'


def depth(term):
    return term.height
