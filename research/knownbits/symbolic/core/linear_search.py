"""Untrusted exact Fourier--Motzkin search for linear contradiction witnesses.

An input row is ``{"coeff": {variable: integer, ...}, "bound": integer}``
and means ``sum(coeff[v] * v) <= bound``.  Variables may be integers, but
this producer only searches the real relaxation; it never rounds inequalities.
Every ``unsat`` result supplies nonnegative rational weights on ORIGINAL rows.
An independent checker must verify their combination has zero coefficients and
a strictly negative bound.  No other result is a satisfiability claim.

``max_rows`` caps the total number of row constructions, including input rows
and pair consequences later discarded as duplicates or tautologies.  It is not
an execution-time or memory-byte bound; callers can enforce a wall-clock limit.
"""

from fractions import Fraction
from math import gcd


def _normalize(coeff, bound, weights):
    """Only positive, exact rescaling; retain an original-row derivation."""
    coeff = {v: a for v, a in coeff.items() if a}
    divisor = abs(bound)
    for value in coeff.values():
        divisor = gcd(divisor, abs(value))
    if divisor > 1:
        coeff = {v: a // divisor for v, a in coeff.items()}
        bound //= divisor
        weights = {i: w / divisor for i, w in weights.items() if w}
    return coeff, bound, weights


def _combine(positive, negative, variable):
    pc, pb, pw = positive
    nc, nb, nw = negative
    pscale, nscale = -nc[variable], pc[variable]
    coeff = {v: pscale * a for v, a in pc.items()}
    for v, a in nc.items():
        coeff[v] = coeff.get(v, 0) + nscale * a
    weights = {i: pscale * w for i, w in pw.items()}
    for i, w in nw.items():
        weights[i] = weights.get(i, Fraction(0)) + nscale * w
    return _normalize(coeff, pscale * pb + nscale * nb, weights)


def refute(rows, max_rows=20000):
    """Return a checked-externally Farkas witness, or ``status='unknown'``.

    Output weights are ``[original_row_index, numerator, denominator]`` triples.
    Search chooses the variable minimizing positive-row count times negative-row
    count.  With a one-sided variable, all rows containing it can be projected
    away.  Identical coefficient maps retain only their strongest bound.
    """
    stats = {
        "input_rows": len(rows),
        "constructed_rows": 0,
        "generated_rows": 0,
        "peak_rows": 0,
        "eliminations": 0,
        "elimination_order": [],
        "duplicate_rows": 0,
        "tautologies": 0,
        "one_sided_rows_removed": 0,
        "max_rows": max_rows,
    }

    def unknown(reason):
        return {"status": "unknown", "reason": reason, "stats": stats}

    def contradiction(row):
        return {
            "status": "unsat",
            "weights": [[i, w.numerator, w.denominator]
                        for i, w in sorted(row[2].items()) if w],
            "stats": stats,
        }

    if type(max_rows) is not int or max_rows < 1:
        return unknown("invalid_row_limit")

    def retain(table, row):
        """Return a contradiction row if present; otherwise update table."""
        coeff, bound, _ = row
        if not coeff:
            if bound < 0:
                return row
            stats["tautologies"] += 1
            return None
        key = tuple(sorted(coeff.items()))
        previous = table.get(key)
        if previous is not None:
            stats["duplicate_rows"] += 1
        if previous is None or bound < previous[1]:
            table[key] = row
        stats["peak_rows"] = max(stats["peak_rows"], len(table))
        return None

    active = {}
    for index, source in enumerate(rows):
        if stats["constructed_rows"] >= max_rows:
            return unknown("row_limit")
        if (not isinstance(source, dict)
                or not isinstance(source.get("coeff"), dict)
                or type(source.get("bound")) is not int
                or any(not isinstance(v, str) or type(a) is not int
                       for v, a in source["coeff"].items())):
            return unknown("invalid_input_row")
        stats["constructed_rows"] += 1
        row = _normalize(dict(source["coeff"]), source["bound"],
                         {index: Fraction(1)})
        bad = retain(active, row)
        if bad is not None:
            return contradiction(bad)

    while active:
        counts = {}
        for coeff, _, _ in active.values():
            for variable, value in coeff.items():
                signs = counts.setdefault(variable, [0, 0])
                signs[0 if value > 0 else 1] += 1
        variable = min(counts, key=lambda v: (counts[v][0] * counts[v][1], v))
        positives, negatives, independent = [], [], {}
        for key, row in active.items():
            value = row[0].get(variable, 0)
            if value > 0:
                positives.append(row)
            elif value < 0:
                negatives.append(row)
            else:
                independent[key] = row

        stats["eliminations"] += 1
        stats["elimination_order"].append(variable)
        if not positives or not negatives:
            stats["one_sided_rows_removed"] += len(positives) + len(negatives)
        for positive in positives:
            for negative in negatives:
                if stats["constructed_rows"] >= max_rows:
                    return unknown("row_limit")
                stats["constructed_rows"] += 1
                stats["generated_rows"] += 1
                row = _combine(positive, negative, variable)
                bad = retain(independent, row)
                if bad is not None:
                    return contradiction(bad)
        active = independent

    return unknown("no_real_contradiction")
