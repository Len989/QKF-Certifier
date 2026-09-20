"""Atomic obligations retained from observations.checker, with implicit separation.

The explicit-check prefix is specialized to atomic rows, not dynamically loaded
or executed. Existing checkers remain byte-identical. Predicate origins are
strictly earlier. Distinct block signatures therefore supply a distinguishing
terminal/output context; no list of pair witnesses is needed for minimality.
"""
from research.observations.atomic_rows import check_completion, image as atomic_image
from research.observations.model import ATOMIC_CERT_SCHEMA, CERT_SCHEMA, MAX_ATOMIC_CLASSES, MAX_CLASSES, Model, integer, require


SCHEMA = "qkf-derived-observation-implicit-v1"
POLICY = "first-differing-derived-question-v1"

def check(data, cert):
    m = Model(data)
    require(type(cert) is dict and set(cert) == {
        "schema", "model_sha256", "predicates", "blocks", "initial", "rows", "cells", "separation"
    }, "certificate fields")
    require(cert["schema"] == SCHEMA and cert["separation"] == POLICY and cert["model_sha256"] == m.sha256,
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
    require(type(blocks) is list and 0 < len(blocks) <= MAX_ATOMIC_CLASSES,
            "bounded quotient")
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
        fields = {"symbol", "output", "supplied", "empty", "extension", "kernel_projection"}
        require(type(row) is dict and set(row) == fields, "row proof fields")
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
        check_completion(row, k)
        tables[a, y] = {1 << j: atomic_image(row, 1 << j, k) for j in range(k)}
        supplied_count += len(supplied)
        forced_count += (1 << k) - len(supplied)

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


    return {"status": "certified", "native_states": len(m.states), "classes": k,
            "derived_observations": len(ps), "row_templates": len(rows),
            "supplied_cells": supplied_count, "forced_cells": forced_count,
            "row_encoding": "atomic", "stored_separators": 0,
            "separated_pairs": k * (k-1) // 2,
            "minimality": "coarsest output/terminal-preserving stable partition of this finite model",
            "minimum_question_count_checked": False, "shortest_context_checked": False}


def question(predicates, index):
    """Resolve one already checked origin chain; no pair search or BFS."""
    require(integer(index, 0, len(predicates)-1), "question index")
    word, origin = [], []
    while True:
        p = predicates[index]; origin.append(index)
        if p["kind"] != "pullback": break
        word.append(p["symbol"])
        require(integer(p["parent"], 0, index-1), "earlier question premise")
        index = p["parent"]
    if p["kind"] == "output": word.append(p["symbol"])
    return word, p["kind"] == "terminal", origin


def separator(model, cert, left, right):
    """Internal: caller must have checked model and compact proof first."""
    blocks, ps = cert["blocks"], cert["predicates"]
    require(integer(left, 0, len(blocks)-1) and integer(right, left+1, len(blocks)-1),
            "ordered pair of distinct classes")
    index = next((i for i, p in enumerate(ps)
                  if bool(p["mask"] & (1 << model.index[blocks[left][0]])) !=
                     bool(p["mask"] & (1 << model.index[blocks[right][0]]))), None)
    require(index is not None, "no distinguishing question")
    word, terminal, origin = question(ps, index)
    values = []
    for block in (blocks[left], blocks[right]):
        answers = set()
        for s in block:
            trace, end = model.run(s, word)
            answers.add(model.terminal[end] if terminal else trace[-1])
        require(len(answers) == 1, "context must apply to every block representative")
        values.append(next(iter(answers)))
    require(values[0] != values[1], "question does not separate classes")
    witness = {"left": left, "right": right, "word": word, "terminal": terminal,
               "left_value": values[0], "right_value": values[1]}
    return witness, origin
