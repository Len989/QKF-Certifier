"""Independent replay of target closure over an inferred quotient."""

from research.observations.model import integer, require
from .adapters import quotient_cells


def _table(cells):
    return {(row["state"], row["symbol"]): (row["output"], row["next"]) for row in cells}


def _word_state(value):
    require(type(value) is list and len(value) == 2 and type(value[0]) is int
            and type(value[1]) is list and all(type(x) is int for x in value[1]),
            "word target product state")
    return value[0], tuple(value[1])


def _predicate_state(value):
    require(type(value) is list and len(value) == 3 and all(type(x) is int for x in value[:2])
            and type(value[2]) is bool, "predicate target product state")
    return value[0], value[1], value[2]


def check_target_proof(system, selected, proof):
    blocks, block_of, cells = quotient_cells(system, selected)
    table = _table(cells)
    require(type(proof) is dict and type(proof.get("kind")) is str, "target proof object")

    if system.family == "ascending-region":
        require(proof == {
            "kind": "interface_only",
            "reason": "successor_target_checker_not_connected_v1",
        }, "explicit ascending inference boundary")
        return {"target_status": "not_checked", "target_reason": proof["reason"]}

    if proof["kind"] == "counterexample":
        require(set(proof) == {"kind", "word"}, "target counterexample fields")
        word = proof["word"]
        require(type(word) is list and 0 < len(word) <= 256
                and all(type(x) is str and x in system.alphabet for x in word),
                "target counterexample word")
        q = block_of[system.initial]
        if system.family == "streaming-word":
            from research.wordexpr import semantics as sem
            target = system.target_data["ir"]
            t = sem.goal_initial(target)
            mismatch = False
            for symbol in word:
                actual, q = table[q, symbol]
                expected, t = sem.goal_cell(target, t, symbol)
                mismatch = mismatch or actual != expected
            require(mismatch, "word target witness does not refute")
        else:
            from research.wordexpr.predicate_frontend import target_value
            count, started = 0, False
            mismatch = False
            limit = system.target_data["limit"]
            target = system.target_data["spec"]["target"]
            for symbol in word:
                _, q = table[q, symbol]
                count = min(limit, count + int(symbol))
                started = True
                source_terminal = system.terminal(blocks[q][0])
                expected = str(bool(target_value(target, count))).lower()
                mismatch = mismatch or source_terminal != expected
            require(started and mismatch, "predicate target witness does not refute")
        return {"target_status": "refuted", "witness_width": len(word)}

    require(proof["kind"] == "closure" and set(proof) == {"kind", "states"},
            "target closure fields")
    nodes = proof["states"]
    require(type(nodes) is list and 0 < len(nodes) <= 4096, "target closure state budget")
    states, seen = [], set()

    for i, node in enumerate(nodes):
        require(type(node) is dict and set(node) == {"state", "parent"}, "target closure record")
        raw, parent = node["state"], node["parent"]
        if system.family == "streaming-word":
            state = _word_state(raw)
            from research.wordexpr import semantics as sem
            expected_initial = (block_of[system.initial], sem.goal_initial(system.target_data["ir"]))
        else:
            state = _predicate_state(raw)
            expected_initial = (block_of[system.initial], 0, False)
        require(state not in seen, "distinct target product state")
        if i == 0:
            require(parent is None and state == expected_initial, "target product initial state")
        else:
            require(type(parent) is list and len(parent) == 2 and integer(parent[0], 0, i - 1)
                    and type(parent[1]) is str and parent[1] in system.alphabet,
                    "target product parent")
            previous = states[parent[0]]
            symbol = parent[1]
            if system.family == "streaming-word":
                q, t = previous
                actual, nq = table[q, symbol]
                expected, nt = sem.goal_cell(system.target_data["ir"], t, symbol)
                require(actual == expected and state == (nq, nt), "word target reachability/agreement")
            else:
                from research.wordexpr.predicate_frontend import target_value
                q, count, _started = previous
                _, nq = table[q, symbol]
                nc = min(system.target_data["limit"], count + int(symbol))
                require(state == (nq, nc, True), "predicate target reachability")
                source_terminal = system.terminal(blocks[nq][0])
                expected = str(bool(target_value(system.target_data["spec"]["target"], nc))).lower()
                require(source_terminal == expected, "predicate terminal target agreement")
        states.append(state)
        seen.add(state)

    for state in states:
        for symbol in system.alphabet:
            if system.family == "streaming-word":
                q, t = state
                actual, nq = table[q, symbol]
                expected, nt = sem.goal_cell(system.target_data["ir"], t, symbol)
                require(actual == expected and (nq, nt) in seen, "closed word target product")
            else:
                from research.wordexpr.predicate_frontend import target_value
                q, count, _started = state
                _, nq = table[q, symbol]
                nc = min(system.target_data["limit"], count + int(symbol))
                source_terminal = system.terminal(blocks[nq][0])
                expected = str(bool(target_value(system.target_data["spec"]["target"], nc))).lower()
                require(source_terminal == expected and (nq, nc, True) in seen,
                        "closed predicate target product")

    return {"target_status": "certified", "target_product_states": len(states)}
