"""Replay a proposed observation proof against independently supplied semantics.

No producer, partition search, SMT solver, or certificate-supplied code is run.
All checks use exceptions, including under python -O.
"""
from .model import CERT_SCHEMA, MAX_CLASSES, Model, integer, require


def check(data, cert):
    m = Model(data)
    require(type(cert) is dict and set(cert) == {
        "schema", "model_sha256", "predicates", "blocks", "initial", "rows", "cells", "separators"
    }, "certificate fields")
    require(cert["schema"] == CERT_SCHEMA and cert["model_sha256"] == m.sha256,
            "certificate belongs to a different native model")
    ps = cert["predicates"]
    require(type(ps) is list and len(ps) < len(m.states), "bounded generating questions")
    for i, p in enumerate(ps):
        require(type(p) is dict and p.get("kind") in {"terminal", "output", "pullback"},
                "question derivation")
        require(integer(p.get("mask"), 0, (1 << len(m.states)) - 1), "question mask")
        kind = p["kind"]
        if kind == "terminal":
            require(set(p) == {"kind", "label", "mask"} and type(p["label"]) is str
                    and p["label"] in m.terminal.values(), "terminal question")
            expected = m.mask(lambda s: m.terminal[s] == p["label"])
        else:
            require(type(p.get("symbol")) is str and p["symbol"] in m.alphabet, "question symbol")
            a = p["symbol"]
            if kind == "output":
                require(set(p) == {"kind", "symbol", "label", "mask"}
                        and type(p["label"]) is str and p["label"] in m.outputs, "output question")
                expected = m.mask(lambda s: m.step[s, a][0] == p["label"])
            else:
                require(set(p) == {"kind", "symbol", "parent", "mask"}
                        and integer(p["parent"], 0, i - 1), "acyclic pullback derivation")
                source = ps[p["parent"]]["mask"]
                expected = m.mask(lambda s: source & (1 << m.index[m.step[s, a][1]]))
        require(p["mask"] == expected, "incorrect derived question")

    blocks = cert["blocks"]
    require(type(blocks) is list and 0 < len(blocks) <= MAX_CLASSES, "bounded quotient")
    for b in blocks:
        require(type(b) is list and b and all(type(s) is str and s in m.states for s in b),
                "quotient block")
        require(b == sorted(set(b)), "block uniqueness and order")
    require(blocks == sorted(blocks), "canonical block order")
    require(sorted(s for b in blocks for s in b) == m.states, "partition covers native carrier once")
    block_of = {s: i for i, b in enumerate(blocks) for s in b}
    # Check the proposed kernel directly; do not rerun the producer's closure.
    for s in m.states:
        for t in m.states:
            same_answers = all(bool(p["mask"] & (1 << m.index[s]))
                               == bool(p["mask"] & (1 << m.index[t])) for p in ps)
            require((block_of[s] == block_of[t]) == same_answers, "observation kernel mismatch")
    require(integer(cert["initial"], 0, len(blocks) - 1)
            and cert["initial"] == block_of[m.initial], "initial class")
    native = {}
    for i, b in enumerate(blocks):
        require(len({m.terminal[s] for s in b}) == 1, "terminal labels not protected")
        for a in m.alphabet:
            choices = {(m.step[s, a][0], block_of[m.step[s, a][1]]) for s in b}
            require(len(choices) == 1, "kernel not stable for output and continuation")
            native[a, i] = next(iter(choices))

    k, top = len(blocks), (1 << len(blocks)) - 1
    rows = cert["rows"]
    require(type(rows) is list and len(rows) == len(m.alphabet) * len(m.outputs), "complete row family")
    tables = {}
    supplied_count = forced_count = 0
    for row in rows:
        require(type(row) is dict and set(row) == {
            "symbol", "output", "supplied", "steps", "table", "kernel"
        }, "row proof fields")
        a, y = row["symbol"], row["output"]
        require(type(a) is str and type(y) is str and a in m.alphabet and y in m.outputs,
                "row label")
        require((a, y) not in tables, "duplicate row")
        supplied = row["supplied"]
        expected = [[1 << j, sum(1 << i for i in range(k) if native[a, i] == (y, j))]
                    for j in range(k)]
        if k == 1:
            expected.insert(0, [0, 0])
        require(type(supplied) is list and len(supplied) == len(expected), "native row generators")
        for cell in supplied:
            require(type(cell) is list and len(cell) == 2
                    and all(integer(v, 0, top) for v in cell), "supplied cell type")
        require(supplied == expected, "native atomic labels changed")
        values = dict(supplied)
        steps = row["steps"]
        require(type(steps) is list and len(steps) == (1 << k) - len(values), "forced derivation size")
        for step in steps:
            require(type(step) is dict and set(step) == {"op", "left", "right", "input", "image"},
                    "forced step fields")
            require(all(integer(step[x], 0, top) for x in ("left", "right", "input", "image")),
                    "forced step carrier")
            l, r = step["left"], step["right"]
            require(l in values and r in values and step["op"] in {"union", "intersection"},
                    "known forced row premises")
            union = step["op"] == "union"
            arg = l | r if union else l & r
            image = values[l] | values[r] if union else values[l] & values[r]
            require(arg not in values and step["input"] == arg and step["image"] == image,
                    "invalid forced row consequence")
            values[arg] = image
        table = row["table"]
        require(type(table) is list and len(table) == 1 << k
                and all(integer(v, 0, top) for v in table), "completed row carrier")
        require(set(values) == set(range(1 << k)) and table == [values[i] for i in range(1 << k)],
                "completed row differs from its proof")
        # Native preimages give pairwise-disjoint atom images; together with
        # forced unions this establishes intersection preservation on all sets.
        require(all(table[1 << i] & table[1 << j] == 0 for i in range(k) for j in range(i)),
                "row does not preserve atomic intersections")
        kernel = [[i for i, v in enumerate(table) if v == image] for image in sorted(set(table))]
        require(type(row["kernel"]) is list
                and all(type(b) is list and all(integer(x, 0, top) for x in b) for b in row["kernel"])
                and row["kernel"] == kernel, "row kernel mismatch")
        tables[a, y] = table
        supplied_count += len(supplied)
        forced_count += len(steps)

    expected_cells = []
    for a in m.alphabet:
        for i in range(k):
            choices = [(y, j) for y in m.outputs for j in range(k) if tables[a, y][1 << j] & (1 << i)]
            require(len(choices) == 1 and choices[0] == native[a, i], "labeled row factorization")
            y, j = choices[0]
            expected_cells.append({"symbol": a, "state": i, "output": y, "next": j})
    require(type(cert["cells"]) is list and len(cert["cells"]) == len(expected_cells), "quotient cells")
    for c in cert["cells"]:
        require(type(c) is dict and set(c) == {"symbol", "state", "output", "next"}
                and integer(c["state"], 0, k - 1) and integer(c["next"], 0, k - 1), "quotient cell types")
    require(cert["cells"] == expected_cells, "row consumer table mismatch")

    separators = cert["separators"]
    require(type(separators) is list and len(separators) == k * (k - 1) // 2, "all separating witnesses")
    pairs = set()
    for w in separators:
        require(type(w) is dict and set(w) == {"left", "right", "word", "terminal", "left_value", "right_value"},
                "separating witness fields")
        i, j, word = w["left"], w["right"], w["word"]
        require(integer(i, 0, k - 1) and integer(j, i + 1, k - 1) and (i, j) not in pairs,
                "distinct witness pair")
        pairs.add((i, j))
        require(type(w["terminal"]) is bool and type(word) is list and len(word) <= len(m.states)
                and all(type(a) is str and a in m.alphabet for a in word), "witness context")
        require(w["terminal"] or word, "output witness needs a symbol")
        values = []
        for block in (blocks[i], blocks[j]):
            answers = set()
            for s in block:
                trace, end = m.run(s, word)
                answers.add(m.terminal[end] if w["terminal"] else trace[-1])
            require(len(answers) == 1, "witness must apply to each representative")
            values.append(next(iter(answers)))
        require(values[0] != values[1] and values == [w["left_value"], w["right_value"]],
                "witness does not distinguish the classes")
    return {"status": "certified", "native_states": len(m.states), "classes": k,
            "derived_observations": len(ps), "row_templates": len(rows),
            "supplied_cells": supplied_count, "forced_cells": forced_count,
            "max_witness_length": max((len(w["word"]) for w in separators), default=0),
            "minimality": "coarsest output/terminal-preserving stable partition of this finite model",
            "scope": "all finite symbol traces of the supplied native model; no Java or signed-word theorem"}


def replay(data, cert, word):
    check(data, cert)
    m = Model(data)
    require(all(type(a) is str and a in m.alphabet for a in word), "legal replay symbols")
    tables = {(r["symbol"], r["output"]): r["table"] for r in cert["rows"]}
    state = cert["initial"]
    trace = []
    for a in word:
        choices = [(y, j) for y in m.outputs for j in range(len(cert["blocks"]))
                   if tables[a, y][1 << j] & (1 << state)]
        require(len(choices) == 1, "row replay determinism")
        y, state = choices[0]
        trace.append(y)
    return {"outputs": trace, "class": state,
            "terminal": m.terminal[cert["blocks"][state][0]]}
