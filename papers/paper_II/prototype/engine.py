"""Bounded partial-term congruence; reference engine for the Paper II prototype.

Terms outside the pool are never registered. Operation symbols of A and B
are always namespaced unless merge identifies the action symbol with an
operator operation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from algebras import Algebra, LIBRARY, validate_library


SEP = "::"


class Term(Tuple):
    """Hash-consed term represented as a nested tuple: (head, *args)."""

    def __new__(cls, head: str, args: Sequence["Term"] = ()):
        return tuple.__new__(cls, (head, *args))

    @property
    def head(self) -> str:
        return self[0]

    @property
    def args(self) -> Tuple["Term", ...]:
        return self[1:]

    def pretty(self) -> str:
        if not self.args:
            return self.head
        inner = ",".join(a.pretty() for a in self.args)
        return f"{self.head}({inner})"


def depth(t: Term) -> int:
    if not t.args:
        return 0
    return 1 + max(depth(a) for a in t.args)


def const(name: str) -> Term:
    return Term(name, ())


class UnionFind:
    def __init__(self) -> None:
        self.parent: Dict[Term, Term] = {}

    def add(self, x: Term) -> None:
        self.parent.setdefault(x, x)

    def find(self, x: Term) -> Term:
        p = self.parent[x]
        if p != x:
            self.parent[x] = self.find(p)
        return self.parent[x]

    def union(self, a: Term, b: Term) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        # keep a stable representative: shorter depth, then pretty
        if (depth(rb), rb.pretty()) < (depth(ra), ra.pretty()):
            ra, rb = rb, ra
        self.parent[rb] = ra
        return True


def ns(prefix: str, raw: str) -> str:
    return f"{prefix}{SEP}{raw}"


def namespaced_constants(alg: Algebra, prefix: str) -> List[Term]:
    return [const(ns(prefix, c)) for c in alg.carrier]


def op_name(prefix: str, op: str) -> str:
    return ns(prefix, op)


def instantiate_term(raw_head: str, raw_args: Sequence[str], prefix: str) -> Term:
    return Term(op_name(prefix, raw_head), tuple(const(ns(prefix, a)) for a in raw_args))


@dataclass
class Theory:
    A: Algebra
    B: Algebra
    ident: str = "none"
    schemes: Tuple[str, ...] = ()
    merge: bool = False
    merge_op: Optional[str] = None
    tab: Optional[Dict[Tuple[str, str], str]] = None  # finite raw rows (b,a) -> c in A; may be partial


@dataclass
class Result:
    n_classes: int
    with_const: int
    free: int
    n_eq_admitted: int
    n_eq_generated: int
    pool_size: int
    max_depth: int
    collapse: bool
    action_closed: bool
    carrier_classes: Dict[str, str]
    classes_of_action: Dict[str, str]
    pool: List[Term] = field(repr=False, default_factory=list)
    uf: Optional[UnionFind] = field(repr=False, default=None)


def _binary_ops(alg: Algebra) -> List[str]:
    return [op for op, ar in alg.operations.items() if ar == 2]


def _has_const(alg: Algebra, raw: str) -> bool:
    return raw in alg.carrier


def build_signature(th: Theory) -> Tuple[str, Dict[str, int], List[Term], List[Term]]:
    """Return (action_head, ops, C_A terms, C_B terms)."""
    ops: Dict[str, int] = {}
    for op, ar in th.A.operations.items():
        ops[op_name("A", op)] = ar
    for op, ar in th.B.operations.items():
        ops[op_name("B", op)] = ar
    C_A = namespaced_constants(th.A, "A")
    C_B = namespaced_constants(th.B, "B")
    if th.merge:
        mop = th.merge_op or (_binary_ops(th.B)[0] if _binary_ops(th.B) else None)
        if mop is None:
            raise ValueError("merge requested but B has no binary operation")
        action = op_name("B", mop)
    else:
        action = "alpha"
        ops[action] = 2
    return action, ops, C_A, C_B


def generate_equations(th: Theory, action: str) -> List[Tuple[Term, Term]]:
    eqs: List[Tuple[Term, Term]] = []
    C_A = namespaced_constants(th.A, "A")
    C_B = namespaced_constants(th.B, "B")

    # D_A
    for op, args, result in th.A.diagram_rows():
        left = instantiate_term(op, args, "A")
        right = const(ns("A", result))
        eqs.append((left, right))
    # D_B (as equations on B-terms; transferred rows are listed explicitly
    # below for bookkeeping although they are redundant under congruence)
    dB: List[Tuple[Term, Term]] = []
    for op, args, result in th.B.diagram_rows():
        left = instantiate_term(op, args, "B")
        right = const(ns("B", result))
        eqs.append((left, right))
        dB.append((left, right))

    # Explicit transfer bookkeeping. In the full equational theory these rows
    # already follow from D_B by congruence; keeping them preserves the frozen
    # bounded-protocol specification used for the published computations.
    for t, s in dB:
        for a in C_A:
            eqs.append((Term(action, (t, a)), Term(action, (s, a))))

    # compatibility: positive-arity ops of A, ranges b in C_B, a_i in C_A
    for op, ar in th.A.operations.items():
        if ar <= 0:
            continue
        f = op_name("A", op)
        for b in C_B:
            for tup in product(C_A, repeat=ar):
                inner = Term(f, tup)
                left = Term(action, (b, inner))
                right = Term(f, tuple(Term(action, (b, ai)) for ai in tup))
                eqs.append((left, right))

    # identifications
    raw_A = set(th.A.carrier)
    raw_B = set(th.B.carrier)
    pairs: List[Tuple[str, str]] = []
    if th.ident == "zeros":
        if "0" in raw_A and "0" in raw_B:
            pairs.append(("0", "0"))
    elif th.ident == "neutrals":
        if "0" in raw_A and "0" in raw_B:
            pairs.append(("0", "0"))
        if "1" in raw_A and "1" in raw_B:
            pairs.append(("1", "1"))
    elif th.ident == "by_name":
        for c in raw_A & raw_B:
            pairs.append((c, c))
    elif th.ident == "none":
        pass
    else:
        raise ValueError(f"unknown identification axis {th.ident}")
    for ca, cb in pairs:
        eqs.append((const(ns("A", ca)), const(ns("B", cb))))

    schemes = set(th.schemes)
    if "Un" in schemes:
        unit_raw = th.B.unit if th.B.unit is not None else ("1" if _has_const(th.B, "1") else None)
        if unit_raw is None or not _has_const(th.B, unit_raw):
            raise ValueError("Un requires a unit constant on B (1 or Algebra.unit)")
        one = const(ns("B", unit_raw))
        for a in C_A:
            eqs.append((Term(action, (one, a)), a))
    if "Ann" in schemes:
        zB_raw = th.B.zero if th.B.zero is not None else ("0" if _has_const(th.B, "0") else None)
        zA_raw = th.A.zero if th.A.zero is not None else ("0" if _has_const(th.A, "0") else None)
        if zB_raw is None or zA_raw is None:
            raise ValueError("Ann requires zero constants on A and B")
        zB, zA = const(ns("B", zB_raw)), const(ns("A", zA_raw))
        for a in C_A:
            eqs.append((Term(action, (zB, a)), zA))
    if "Dist" in schemes:
        # scalar Dist uses carrier addition A::+ or A::⊕ if present
        add = None
        for cand in ("+", "⊕"):
            if cand in th.A.operations and th.A.operations[cand] == 2:
                add = op_name("A", cand)
                break
        if add is None:
            raise ValueError("Dist requires a binary addition-like operation on A")
        for b1, b2 in product(C_B, repeat=2):
            for a in C_A:
                left = Term(action, (Term(add, (b1, b2)), a))
                right = Term(add, (Term(action, (b1, a)), Term(action, (b2, a))))
                eqs.append((left, right))
    if "Hom" in schemes:
        raise ValueError("Hom is not a published scheme; use Comp for group composition")
    if "Comp" in schemes:
        muls = [op for op, ar in th.B.operations.items() if ar == 2]
        if not muls:
            raise ValueError("Comp requires a binary operation on B")
        mul = op_name("B", muls[0])
        for g, h in product(C_B, repeat=2):
            for a in C_A:
                left = Term(action, (Term(mul, (g, h)), a))
                right = Term(action, (g, Term(action, (h, a))))
                eqs.append((left, right))
    if "Inv" in schemes:
        if "inv" not in th.B.operations:
            raise ValueError("Inv requires a unary inv on B")
        inv = op_name("B", "inv")
        for b in C_B:
            ib = Term(inv, (b,))
            for a in C_A:
                eqs.append((Term(action, (ib, Term(action, (b, a)))), a))
    if "Tab" in schemes:
        if th.tab is None:
            raise ValueError("Tab requires th.tab")
        for (b_raw, a_raw), c_raw in th.tab.items():
            eqs.append(
                (
                    Term(action, (const(ns("B", b_raw)), const(ns("A", a_raw)))),
                    const(ns("A", c_raw)),
                )
            )
    return eqs


def build_pool(ops: Dict[str, int], constants: List[Term], d: int, cap: int) -> List[Term]:
    """Enumerate T^{(d)} or a depth-ordered truncation."""
    seen: Set[Term] = set()
    levels: List[List[Term]] = [list(constants)]
    for t in constants:
        seen.add(t)
    # include declared 0-ary ops that are not already constants
    for op, ar in ops.items():
        if ar == 0:
            t = Term(op, ())
            if t not in seen:
                seen.add(t)
                levels[0].append(t)

    def arg_pool() -> List[Term]:
        flat = [t for lvl in levels for t in lvl]
        flat.sort(key=lambda t: (depth(t), t.pretty()))
        if cap and cap > 0:
            return flat[:cap]
        return flat

    for _ in range(1, d + 1):
        new_level: List[Term] = []
        pool = arg_pool() if cap and cap > 0 else [t for lvl in levels for t in lvl]
        if not (cap and cap > 0):
            pool.sort(key=lambda t: (depth(t), t.pretty()))
        for op, ar in ops.items():
            if ar <= 0:
                continue
            for args in product(pool, repeat=ar):
                t = Term(op, args)
                if t not in seen:
                    seen.add(t)
                    new_level.append(t)
        levels.append(new_level)
    return [t for lvl in levels for t in lvl]


def close(pool: Sequence[Term], eqs: Sequence[Tuple[Term, Term]], ops: Dict[str, int]) -> Tuple[UnionFind, int]:
    P: Set[Term] = set(pool)
    uf = UnionFind()
    for t in pool:
        uf.add(t)
    admitted = [(l, r) for l, r in eqs if l in P and r in P]
    by_head: Dict[str, List[Term]] = {}
    for t in pool:
        if t.args:
            by_head.setdefault(t.head, []).append(t)

    changed = True
    while changed:
        changed = False
        for l, r in admitted:
            if uf.union(l, r):
                changed = True
        for head, terms in by_head.items():
            buckets: Dict[Tuple[Term, ...], Term] = {}
            for t in terms:
                sig = tuple(uf.find(a) for a in t.args)
                if sig in buckets:
                    if uf.union(buckets[sig], t):
                        changed = True
                else:
                    buckets[sig] = t
    return uf, len(admitted)


def synthesize(
    A: Algebra,
    B: Algebra,
    d: int,
    cap: int = 0,
    ident: str = "none",
    schemes: Sequence[str] = (),
    merge: bool = False,
    merge_op: Optional[str] = None,
    tab: Optional[Dict[Tuple[str, str], str]] = None,
) -> Result:
    th = Theory(
        A=A,
        B=B,
        ident=ident,
        schemes=tuple(schemes),
        merge=merge,
        merge_op=merge_op,
        tab=tab,
    )
    action, ops, C_A, C_B = build_signature(th)
    eqs = generate_equations(th, action)
    constants = list(C_A) + list(C_B)
    pool = build_pool(ops, constants, d, cap)
    if any(depth(t) > d for t in pool):
        raise RuntimeError("pool contains a term deeper than d")
    uf, n_adm = close(pool, eqs, ops)

    classes: Dict[Term, List[Term]] = {}
    for t in pool:
        classes.setdefault(uf.find(t), []).append(t)

    carrier_set = set(C_A)
    with_const = 0
    for members in classes.values():
        if any(m in carrier_set for m in members):
            with_const += 1
    n = len(classes)
    roots_A = {uf.find(c) for c in C_A}
    collapse = len(C_A) > 1 and len(roots_A) == 1

    action_map = {}
    closed = True
    for b in C_B:
        for a in C_A:
            t = Term(action, (b, a))
            if t not in uf.parent:
                closed = False
                action_map[t.pretty()] = "NOT_IN_POOL"
                continue
            root = uf.find(t)
            members = classes[root]
            hit = next((m.pretty() for m in members if m in carrier_set), None)
            action_map[t.pretty()] = hit or root.pretty()
            if hit is None:
                closed = False

    return Result(
        n_classes=n,
        with_const=with_const,
        free=n - with_const,
        n_eq_admitted=n_adm,
        n_eq_generated=len(eqs),
        pool_size=len(pool),
        max_depth=max(depth(t) for t in pool) if pool else 0,
        collapse=collapse,
        action_closed=closed,
        carrier_classes={c.pretty(): uf.find(c).pretty() for c in C_A},
        classes_of_action=action_map,
        pool=list(pool),
        uf=uf,
    )


def identity_table(A: Algebra, B: Algebra) -> Dict[Tuple[str, str], str]:
    """α(b,a)=a for every b (requires no extra structure)."""
    return {(b, a): a for b in B.carrier for a in A.carrier}


def flip_table_z2(B: Algebra) -> Dict[Tuple[str, str], str]:
    """Non-identity involution on Z/2 = {0,1}, independent of B-element except we need all pairs."""
    flip = {"0": "1", "1": "0"}
    return {(b, a): flip[a] for b in B.carrier for a in ("0", "1")}


def sign_table_z3(B: Algebra) -> Dict[Tuple[str, str], str]:
    """A homomorphism S3 -> Aut(Z/3) via the sign character acting as ±1."""
    # Aut(Z/3) = {id, inversion x |-> -x}. Sign of S3: A3 even, transpositions odd.
    even = {"e", "r", "r2"}
    def act(g: str, a: str) -> str:
        x = int(a)
        if g in even:
            return str(x)
        return str((-x) % 3)
    return {(g, a): act(g, a) for g in B.carrier for a in ("0", "1", "2")}



def parity_table_z4(B: Algebra) -> Dict[Tuple[str, str], str]:
    """Table used in Example 5.24: x |-> x mod 2 represented by 0 or 1 in Z/4."""
    tau = {"0": "0", "1": "1", "2": "0", "3": "1"}
    return {(b, a): tau[a] for b in B.carrier for a in ("0", "1", "2", "3")}

def bad_table_z2(B: Algebra) -> Dict[Tuple[str, str], str]:
    """Not a homomorphism: send everything to 1 except (e,0)->0 or similar junk."""
    tab = {}
    for g in B.carrier:
        for a in ("0", "1"):
            tab[(g, a)] = "1"
    tab[("e", "0")] = "0"
    return tab


def bad_table_z3(B: Algebra) -> Dict[Tuple[str, str], str]:
    tab = {}
    for g in B.carrier:
        for a in ("0", "1", "2"):
            tab[(g, a)] = "0"
    tab[("e", "1")] = "1"
    return tab


if __name__ == "__main__":
    validate_library()
    print("library ok", list(LIBRARY))
