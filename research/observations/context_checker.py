"""Independent row and shared-cut certificate replay; no producer or search."""
from .atomic_rows import Table, check_completion
from .context_model import ATOMIC_CERT_SCHEMA, CERT_SCHEMA, MAX_PRODUCT, MAX_STATES, ContextModel
from .model import integer, require


def _tables(m, rows, atomic=False):
    require(type(rows) is list and len(rows) == len(m.rows), "complete context row proofs")
    tables = {}
    k, top = len(m.contexts), m.top
    supplied_count = forced_count = 0
    for row in rows:
        fields = {"control", "symbol", "supplied"} | (
            {"empty", "extension", "kernel_projection"} if atomic else {"steps", "table", "kernel"})
        require(type(row) is dict and set(row) == fields, "context row proof fields")
        c, a = row["control"], row["symbol"]
        require(type(c) is str and type(a) is str and (c, a) in m.rows
                and (c, a) not in tables, "unique native context row")
        edges = m.rows[c, a][1]
        expected = [[1 << j, sum(1 << m.index[h] for h, b in edges.items() if b == target)]
                    for j, target in enumerate(m.contexts)]
        if k == 1:
            expected.insert(0, [0, 0])
        supplied = row["supplied"]
        require(type(supplied) is list and all(type(cell) is list and len(cell) == 2
                and all(integer(v, 0, top) for v in cell) for cell in supplied)
                and supplied == expected, "context native atoms changed")
        values = dict(supplied)
        if atomic:
            check_completion(row, k)
            tables[c, a] = Table(row, k)
            supplied_count += len(supplied)
            forced_count += (1 << k) - len(supplied)
            continue
        steps = row["steps"]
        require(type(steps) is list and len(steps) == (1 << k) - len(values), "context forced proof size")
        for step in steps:
            require(type(step) is dict and set(step) == {"op", "left", "right", "input", "image"}
                    and all(integer(step[x], 0, top) for x in ("left", "right", "input", "image")),
                    "context forced step types")
            l, r = step["left"], step["right"]
            require(l in values and r in values and step["op"] in {"union", "intersection"},
                    "context forced premises")
            union = step["op"] == "union"
            arg = l | r if union else l & r
            image = values[l] | values[r] if union else values[l] & values[r]
            require(arg not in values and step["input"] == arg and step["image"] == image,
                    "context forced consequence")
            values[arg] = image
        table = row["table"]
        require(type(table) is list and len(table) == 1 << k
                and all(integer(v, 0, top) for v in table), "context row table types")
        require(set(values) == set(range(1 << k)) and table == [values[i] for i in range(1 << k)],
                "context table not derived from proof")
        require(all(table[1 << i] & table[1 << j] == 0 for i in range(k) for j in range(i)),
                "context row atomic intersection")
        kernel = [[i for i, v in enumerate(table) if v == image] for image in sorted(set(table))]
        require(type(row["kernel"]) is list and all(type(b) is list
                and all(integer(v, 0, top) for v in b) for b in row["kernel"])
                and row["kernel"] == kernel, "context row kernel")
        tables[c, a] = table
        supplied_count += len(supplied)
        forced_count += len(steps)
    return tables, supplied_count, forced_count


def check(data, cert):
    m = ContextModel(data)
    require(type(cert) is dict and set(cert) == {
        "schema", "model_sha256", "initial", "rows", "states", "cells", "gap"
    }, "context certificate fields")
    require(cert["schema"] in {CERT_SCHEMA, ATOMIC_CERT_SCHEMA} and cert["model_sha256"] == m.sha256,
            "context certificate belongs to a different native model")
    atomic = cert["schema"] == ATOMIC_CERT_SCHEMA
    tables, supplied, forced = _tables(m, cert["rows"], atomic)
    states = cert["states"]
    require(type(states) is list and 0 < len(states) <= MAX_STATES, "bounded residual states")
    require(integer(cert["initial"], 0, 0), "context initial state id")
    pairs = {}
    for i, state in enumerate(states):
        require(type(state) is dict and set(state) == {"control", "allowed", "parent", "accept"},
                "residual state fields")
        c, mask = state["control"], state["allowed"]
        require(type(c) is str and c in m.controls and integer(mask, 0, m.top), "residual state carrier")
        require((c, mask) not in pairs, "duplicate residual state")
        pairs[c, mask] = i
        require(type(state["accept"]) is bool
                and state["accept"] == bool(mask & (1 << m.index[m.boundary])), "shared top boundary")
        parent = state["parent"]
        if i == 0:
            require(parent is None and (c, mask) == (m.initial, m.bottom), "context start boundary")
        else:
            require(type(parent) is dict and set(parent) == {"state", "symbol"}
                    and integer(parent["state"], 0, i - 1)
                    and type(parent["symbol"]) is str and parent["symbol"] in m.alphabet,
                    "acyclic residual reachability")
            old = states[parent["state"]]
            a = parent["symbol"]
            require((c, mask) == (m.rows[old["control"], a][0], tables[old["control"], a][old["allowed"]]),
                    "residual reachability edge")
    cells = cert["cells"]
    require(type(cells) is list and len(cells) == len(states) * len(m.alphabet), "complete residual transitions")
    actual = {}
    for cell in cells:
        require(type(cell) is dict and set(cell) == {"state", "symbol", "next"}
                and integer(cell["state"], 0, len(states) - 1)
                and integer(cell["next"], 0, len(states) - 1)
                and type(cell["symbol"]) is str and cell["symbol"] in m.alphabet,
                "residual transition types")
        i, a, j = cell["state"], cell["symbol"], cell["next"]
        require((i, a) not in actual, "duplicate residual transition")
        actual[i, a] = j
        c, mask = states[i]["control"], states[i]["allowed"]
        target = (m.rows[c, a][0], tables[c, a][mask])
        require(target in pairs and pairs[target] == j, "transition must consume the forced row")
    gap = cert["gap"]
    if gap is not None:
        require(type(gap) is dict and set(gap) == {"word", "trace", "conflict"}, "context loss witness fields")
        word = gap["word"]
        require(type(word) is list and 0 < len(word) <= MAX_PRODUCT
                and all(type(a) is str and a in m.alphabet for a in word), "context loss word")
        c, exact, weak = m.initial, m.bottom, m.bottom
        trace = [{"control": c, "exact": exact, "independent": weak}]
        for a in word:
            prior_c, prior_exact = c, exact
            table = tables[c, a]
            exact, weak = table[exact], table[m.top if weak else 0]
            c = m.rows[c, a][0]
            trace.append({"control": c, "exact": exact, "independent": weak})
        require(type(gap["trace"]) is list and len(gap["trace"]) == len(trace), "context trace length")
        for point in gap["trace"]:
            require(type(point) is dict and set(point) == {"control", "exact", "independent"}
                    and type(point["control"]) is str and point["control"] in m.controls
                    and all(integer(point[k], 0, m.top) for k in ("exact", "independent")), "context trace types")
        require(gap["trace"] == trace, "context trace replay")
        bit = 1 << m.index[m.boundary]
        require(weak & bit and not exact & bit, "witness must expose a lost shared constraint")
        below = m.rows[prior_c, word[-1]][1][m.boundary]
        expected = {"position": len(word) - 1, "above": m.boundary, "below": below,
                    "required_below": m.members(prior_exact)}
        conflict = gap["conflict"]
        require(type(conflict) is dict and type(conflict.get("position")) is int
                and conflict == expected and below not in expected["required_below"], "lost cut membership")
    return {"status": "certified", "native_contexts": len(m.contexts), "forward_controls": len(m.controls),
            "residual_states": len(states), "row_templates": len(tables), "supplied_cells": supplied,
            "forced_cells": forced, "transitions": len(cells),
            "context_loss_witness_length": 0 if gap is None else len(gap["word"]),
            "scope": "all finite words of supplied local constraints with the declared shared cuts and boundaries",
            "minimality": "not claimed", "absence_of_gap_certified": False,
            **({"row_encoding": "atomic", "stored_forced_steps": 0} if atomic else {})}


def accepts(data, cert, word):
    """Check once, then run the certified residual transition table."""
    check(data, cert)
    m = ContextModel(data)
    require(type(word) is list and all(type(a) is str and a in m.alphabet for a in word), "context replay word")
    cells = {(c["state"], c["symbol"]): c["next"] for c in cert["cells"]}
    state = cert["initial"]
    for a in word:
        state = cells[state, a]
    return cert["states"][state]["accept"]
