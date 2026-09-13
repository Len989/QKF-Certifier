"""Consumer-driven backward closure and forced powerset rows.

This module proposes certificates. The checker never imports it.
"""
from collections import defaultdict

from .model import CERT_SCHEMA, MAX_CLASSES, Model, integer, require


def _partition(model, predicates):
    groups = defaultdict(list)
    for i, state in enumerate(model.states):
        groups[tuple(bool(p["mask"] & (1 << i)) for p in predicates)].append(state)
    return sorted(groups.values())


def _splits(model, blocks, mask):
    return any(len({bool(mask & (1 << model.index[s])) for s in block}) > 1
               for block in blocks)


def _row(atoms):
    k = len(atoms)
    known = {1 << j: value for j, value in enumerate(atoms)}
    supplied = [[s, y] for s, y in sorted(known.items())]
    steps = []
    if k == 1:
        # Atomic intersection cannot generate empty on a one-element carrier.
        supplied.insert(0, [0, 0])
    else:
        steps.append({"op": "intersection", "left": 1, "right": 2, "input": 0, "image": 0})
    known[0] = 0
    for subset in range(1 << k):
        if subset not in known:
            left = subset & -subset
            right = subset ^ left
            known[subset] = known[left] | known[right]
            steps.append({"op": "union", "left": left, "right": right,
                          "input": subset, "image": known[subset]})
    table = [known[i] for i in range(1 << k)]
    kernel = [[i for i, x in enumerate(table) if x == v] for v in sorted(set(table))]
    return {"supplied": supplied, "steps": steps, "table": table, "kernel": kernel}


def synthesize(data, *, max_observations=63, max_pullbacks=4096, max_classes=MAX_CLASSES):
    model = Model(data)
    require(integer(max_observations, 0, 63) and integer(max_pullbacks, 0, 100000)
            and integer(max_classes, 1, MAX_CLASSES), "producer budgets")
    predicates = []
    blocks = [model.states]
    pullbacks = 0

    def exhausted(reason):
        return {"status": "budget_exhausted", "reason": reason, "certificate": None,
                "observations": len(predicates), "classes": len(blocks), "pullbacks": pullbacks}

    def add(proof):
        nonlocal blocks
        if not _splits(model, blocks, proof["mask"]):
            return True
        if len(predicates) == max_observations:
            return False
        predicates.append(proof)
        blocks = _partition(model, predicates)
        return True

    for label in sorted(set(model.terminal.values())):
        if not add({"kind": "terminal", "label": label,
                    "mask": model.mask(lambda s: model.terminal[s] == label)}):
            return exhausted("observation budget")
    for a in model.alphabet:
        for y in model.outputs:
            if not add({"kind": "output", "symbol": a, "label": y,
                        "mask": model.mask(lambda s: model.step[s, a][0] == y)}):
                return exhausted("observation budget")
    # Pullback preserves the Boolean algebra of questions. Only a question
    # splitting an existing atom needs to be added to its generating family.
    i = 0
    while i < len(predicates):
        mask = predicates[i]["mask"]
        for a in model.alphabet:
            if pullbacks == max_pullbacks:
                return exhausted("pullback budget")
            pullbacks += 1
            back = model.mask(lambda s: mask & (1 << model.index[model.step[s, a][1]]))
            if not add({"kind": "pullback", "symbol": a, "parent": i, "mask": back}):
                return exhausted("observation budget")
        i += 1
    if len(blocks) > max_classes:
        return exhausted("complete row carrier budget")

    block_of = {s: i for i, block in enumerate(blocks) for s in block}
    native = {(a, i): (model.step[block[0], a][0], block_of[model.step[block[0], a][1]])
              for a in model.alphabet for i, block in enumerate(blocks)}
    rows = []
    for a in model.alphabet:
        for y in model.outputs:
            atoms = [sum(1 << i for i in range(len(blocks)) if native[a, i] == (y, j))
                     for j in range(len(blocks))]
            rows.append({"symbol": a, "output": y, **_row(atoms)})
    # The continuation actually consumed below is reconstructed from the
    # completed rows, rather than copied from the native transition table.
    cells = []
    for a in model.alphabet:
        for i in range(len(blocks)):
            choices = [(r["output"], j) for r in rows if r["symbol"] == a
                       for j in range(len(blocks)) if r["table"][1 << j] & (1 << i)]
            require(len(choices) == 1, "forced row did not label a unique continuation")
            y, j = choices[0]
            cells.append({"symbol": a, "state": i, "output": y, "next": j})

    def question(index):
        p = predicates[index]
        if p["kind"] == "pullback":
            word, terminal = question(p["parent"])
            return [p["symbol"]] + word, terminal
        return ([], True) if p["kind"] == "terminal" else ([p["symbol"]], False)

    def value(state, word, terminal):
        trace, end = model.run(state, word)
        return model.terminal[end] if terminal else trace[-1]

    separators = []
    for i, left in enumerate(blocks):
        for j in range(i + 1, len(blocks)):
            right = blocks[j]
            p = next(p for p in range(len(predicates))
                     if bool(predicates[p]["mask"] & (1 << model.index[left[0]]))
                     != bool(predicates[p]["mask"] & (1 << model.index[right[0]])))
            word, terminal = question(p)
            separators.append({"left": i, "right": j, "word": word, "terminal": terminal,
                               "left_value": value(left[0], word, terminal),
                               "right_value": value(right[0], word, terminal)})
    certificate = {"schema": CERT_SCHEMA, "model_sha256": model.sha256,
                   "predicates": predicates, "blocks": blocks, "initial": block_of[model.initial],
                   "rows": rows, "cells": cells, "separators": separators}
    return {"status": "candidate", "certificate": certificate,
            "observations": len(predicates), "classes": len(blocks), "pullbacks": pullbacks}
