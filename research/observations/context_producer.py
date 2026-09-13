"""Force local preimage rows, compose residuals, then look for a lost shared cut."""
from collections import deque

from .context_model import CERT_SCHEMA, MAX_PRODUCT, MAX_STATES, ContextModel
from .model import integer, require
from .producer import _row


def synthesize(data, *, max_states=MAX_STATES, max_product=MAX_PRODUCT):
    m = ContextModel(data)
    require(integer(max_states, 1, MAX_STATES) and integer(max_product, 1, MAX_PRODUCT),
            "context producer budgets")
    rows = []
    tables = {}
    for c in m.controls:
        for a in m.alphabet:
            _, edges = m.rows[c, a]
            atoms = [sum(1 << m.index[h] for h, below in edges.items() if below == target)
                     for target in m.contexts]
            proof = _row(atoms)
            rows.append({"control": c, "symbol": a, **proof})
            tables[c, a] = proof["table"]

    def exhausted(reason):
        return {"status": "budget_exhausted", "reason": reason, "certificate": None}

    start = (m.initial, m.bottom)
    nodes = [start]
    ids = {start: 0}
    parents = [None]
    cells = []
    for i, (c, mask) in enumerate(nodes):
        for a in m.alphabet:
            n = (m.rows[c, a][0], tables[c, a][mask])
            if n not in ids:
                if len(nodes) == max_states:
                    return exhausted("residual state budget")
                ids[n] = len(nodes)
                nodes.append(n)
                parents.append({"state": i, "symbol": a})
            cells.append({"state": i, "symbol": a, "next": ids[n]})

    # Ablation: replace every nonempty residual by TOP before the next cell.
    # Keep local guards, forward control, empty failures and the top boundary.
    origin = (m.initial, m.bottom, m.bottom)
    queue = deque([origin])
    pred = {origin: None}
    found = None
    boundary_bit = 1 << m.index[m.boundary]
    while queue:
        c, exact, weak = current = queue.popleft()
        if weak & boundary_bit and not exact & boundary_bit:
            found = current
            break
        for a in m.alphabet:
            row = tables[c, a]
            n = (m.rows[c, a][0], row[exact], row[m.top if weak else 0])
            if n not in pred:
                if len(pred) == max_product:
                    return exhausted("context erasure search budget")
                pred[n] = (current, a)
                queue.append(n)
    gap = None
    if found is not None:
        word, trace = [], [found]
        cursor = found
        while pred[cursor] is not None:
            cursor, a = pred[cursor]
            word.append(a)
            trace.append(cursor)
        word.reverse()
        trace.reverse()
        c, exact, _ = trace[-2]
        below = m.rows[c, word[-1]][1][m.boundary]
        gap = {"word": word,
               "trace": [{"control": c, "exact": e, "independent": w} for c, e, w in trace],
               "conflict": {"position": len(word) - 1, "above": m.boundary, "below": below,
                            "required_below": m.members(exact)}}
    cert = {"schema": CERT_SCHEMA, "model_sha256": m.sha256, "initial": 0,
            "rows": rows, "states": [
                {"control": c, "allowed": mask, "parent": parents[i],
                 "accept": bool(mask & boundary_bit)} for i, (c, mask) in enumerate(nodes)],
            "cells": cells, "gap": gap}
    return {"status": "candidate", "certificate": cert, "product_states_visited": len(pred),
            "diagnostic": "context_erasure_counterexample" if gap else "no_counterexample_found"}
