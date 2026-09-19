"""Produce signed terminal predicate proofs; replay is independent."""

from research.observations.model import digest, integer, require
from research.observations.producer import synthesize
from research.wordexpr.checker import MAX_PRODUCT, MAX_STATES
from research.wordexpr.producer import Budget

from .checker import SCHEMA, SOURCE_SCHEMA, check, joint_step, prepare
from .frontend import goal, read_source, target_value
from .semantics import cell, evaluate, initial, model


def derive(source, spec, *, max_states=MAX_STATES, max_product=MAX_PRODUCT):
    goal(spec)
    require(integer(max_states, 1, MAX_STATES) and integer(max_product, 1, MAX_PRODUCT),
            "signed predicate budgets")
    ir = read_source(source, spec["entry"], spec["word_type"])
    first = initial(ir)
    states, rows, ids = [first], [{"state": list(first), "parent": None}], {first: 0}
    for i, state in enumerate(states):
        for symbol in ("0", "1"):
            following = cell(ir, state, symbol)
            if following not in ids:
                if len(states) == max_states:
                    raise Budget("signed predicate residual-state budget")
                ids[following] = len(states)
                states.append(following)
                rows.append({"state": list(following), "parent": [i, symbol]})

    proposed = synthesize(model(ir, states), row_encoding="atomic")
    if proposed["status"] != "candidate":
        raise Budget("signed predicate QKF budget: " + proposed["reason"])
    source_cert = {
        "schema": SOURCE_SCHEMA,
        "ir": ir,
        "carrier": rows,
        "observations": proposed["certificate"],
    }

    limit, ir, _checked, table, terminals, start = prepare(source, spec, source_cert)
    states, rows, ids, paths = [start], [{"state": list(start), "parent": None}], {start: 0}, [""]
    proof = None
    for i, state in enumerate(states):
        for symbol in ("0", "1"):
            following = joint_step(table, limit, state, symbol)
            bits = paths[i] + symbol
            if terminals[following[0]] != target_value(
                spec["target"], following[1], following[2]
            ):
                x = sum(int(bit) << k for k, bit in enumerate(bits))
                proof = {
                    "kind": "counterexample",
                    "bits": bits,
                    "input": x,
                    "output": evaluate(ir, x, len(bits)),
                    "expected": target_value(
                        spec["target"], x.bit_count(), int(bits[-1])
                    ),
                }
                break
            if following not in ids:
                if len(states) == max_product:
                    raise Budget("signed predicate target product budget")
                ids[following] = len(states)
                states.append(following)
                paths.append(bits)
                rows.append({"state": list(following), "parent": [i, symbol]})
        if proof is not None:
            break

    if proof is None:
        proof = {"kind": "closure", "states": rows}
    cert = {
        "schema": SCHEMA,
        "goal_sha256": digest(spec),
        "source": source_cert,
        "proof": proof,
    }
    return cert, check(source, spec, cert)
