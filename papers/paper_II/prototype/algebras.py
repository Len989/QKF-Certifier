"""Published finite total algebras. Every positive-arity operation has a complete table."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


Row = Tuple[str, ...]


@dataclass(frozen=True)
class Algebra:
    name: str
    carrier: Tuple[str, ...]
    operations: Dict[str, int]
    tables: Dict[str, Dict[Row, str]]
    note: str = ""
    unit: str | None = None
    zero: str | None = None

    def diagram_rows(self) -> List[Tuple[str, Row, str]]:
        rows = []
        for op, ar in self.operations.items():
            if ar <= 0:
                continue
            table = self.tables[op]
            expected = 1
            for _ in range(ar):
                expected *= len(self.carrier)
            if len(table) != expected:
                raise ValueError(
                    f"{self.name}.{op} is not total: {len(table)} rows, expected {expected}"
                )
            for args, result in table.items():
                if result not in self.carrier:
                    raise ValueError(f"{self.name}.{op}{args} -> {result} not in carrier")
                rows.append((op, args, result))
        return rows


def _full_binary(carrier: Tuple[str, ...], fn) -> Dict[Row, str]:
    return {(x, y): fn(x, y) for x in carrier for y in carrier}


def _full_unary(carrier: Tuple[str, ...], fn) -> Dict[Row, str]:
    return {(x,): fn(x) for x in carrier}


# A3: total truncated addition on {0, 1/2, 1}. Same numerical table as MV3;
# the two copies remain distinct after namespacing.
_A3_CAR = ("0", "h", "1")
_RANK = {"0": 0, "h": 1, "1": 2}
_UNRANK = {0: "0", 1: "h", 2: "1"}


def _trunc_add(x: str, y: str) -> str:
    return _UNRANK[min(2, _RANK[x] + _RANK[y])]


def _neg(x: str) -> str:
    return _UNRANK[2 - _RANK[x]]


A3 = Algebra(
    name="A3",
    carrier=_A3_CAR,
    operations={"⊕": 2, "¬": 1},
    tables={
        "⊕": _full_binary(_A3_CAR, _trunc_add),
        "¬": _full_unary(_A3_CAR, _neg),
    },
    note="Three-element total algebra with truncated addition; used as a namespaced control copy.",
    unit="1",
    zero="0",
)

MV3 = Algebra(
    name="MV3",
    carrier=_A3_CAR,
    operations={"⊕": 2, "¬": 1},
    tables={
        "⊕": _full_binary(_A3_CAR, _trunc_add),
        "¬": _full_unary(_A3_CAR, _neg),
    },
    note="Three-element Łukasiewicz MV-algebra (total tables).",
    unit="1",
    zero="0",
)


def _zn_add(n: int):
    car = tuple(str(i) for i in range(n))

    def add(x, y):
        return str((int(x) + int(y)) % n)

    def neg(x):
        return str((-int(x)) % n)

    return Algebra(
        name=f"Z{n}+",
        carrier=car,
        operations={"+": 2, "-": 1},
        tables={"+": _full_binary(car, add), "-": _full_unary(car, neg)},
        note=f"Additive group Z/{n}Z.",
        unit="0",
        zero="0",
    )


def _zn_mul(n: int):
    car = tuple(str(i) for i in range(n))

    def mul(x, y):
        return str((int(x) * int(y)) % n)

    return Algebra(
        name=f"M{n}",
        carrier=car,
        operations={"·": 2},
        tables={"·": _full_binary(car, mul)},
        note=f"Multiplicative monoid of Z/{n}Z.",
        unit="1",
        zero="0",
    )


Z2ADD = _zn_add(2)
Z3ADD = _zn_add(3)
Z4ADD = _zn_add(4)
M2 = _zn_mul(2)
M3 = _zn_mul(3)

BOOL2 = Algebra(
    name="Bool2",
    carrier=("0", "1"),
    operations={"∨": 2, "¬": 1},
    tables={
        "∨": _full_binary(("0", "1"), lambda x, y: "1" if "1" in (x, y) else "0"),
        "¬": _full_unary(("0", "1"), lambda x: "1" if x == "0" else "0"),
    },
    note="Two-element Boolean lattice (join and complement).",
    unit="1",
    zero="0",
)


def _s3() -> Algebra:
    # permutations of {0,1,2} as tuples, composition σ∘τ = σ after τ
    e = (0, 1, 2)
    r = (1, 2, 0)       # (0 1 2)
    r2 = (2, 0, 1)      # (0 2 1)
    s = (0, 2, 1)       # (1 2)
    sr = tuple(s[r[i]] for i in range(3))
    sr2 = tuple(s[r2[i]] for i in range(3))
    names = {
        e: "e",
        r: "r",
        r2: "r2",
        s: "s",
        sr: "sr",
        sr2: "sr2",
    }
    inv_names = {v: k for k, v in names.items()}
    carrier = ("e", "r", "r2", "s", "sr", "sr2")

    def compose(x: str, y: str) -> str:
        sx, sy = inv_names[x], inv_names[y]
        # x ∘ y : apply y then x
        res = tuple(sx[sy[i]] for i in range(3))
        return names[res]

    def inverse(x: str) -> str:
        sx = inv_names[x]
        res = tuple(sx.index(i) for i in range(3))
        return names[res]

    return Algebra(
        name="S3",
        carrier=carrier,
        operations={"∘": 2, "inv": 1},
        tables={"∘": _full_binary(carrier, compose), "inv": _full_unary(carrier, inverse)},
        note="Symmetric group S3 with composition and inverse.",
        unit="e",
        zero=None,
    )


S3 = _s3()

ONE = Algebra(
    name="One",
    carrier=("b",),
    operations={},
    tables={},
    note="One-element operator algebra with no positive-arity native operations; used for the Z4 table-forcing control.",
)

LIBRARY = {
    A3.name: A3,
    MV3.name: MV3,
    Z2ADD.name: Z2ADD,
    Z3ADD.name: Z3ADD,
    Z4ADD.name: Z4ADD,
    M2.name: M2,
    M3.name: M3,
    BOOL2.name: BOOL2,
    S3.name: S3,
    ONE.name: ONE,
}


def validate_library() -> None:
    for alg in LIBRARY.values():
        alg.diagram_rows()
        for c in alg.carrier:
            if "::" in c:
                raise ValueError(f"raw carrier name must not contain '::': {c}")


if __name__ == "__main__":
    validate_library()
    for name, alg in LIBRARY.items():
        n_rows = sum(len(t) for t in alg.tables.values())
        print(f"{name}: |A|={len(alg.carrier)} rows={n_rows} {alg.note}")
