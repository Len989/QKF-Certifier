"""Independent replay for signed terminal predicate certificates."""

from research.observations.checker import check as check_observations
from research.observations.model import digest, integer, require
from research.wordexpr.checker import MAX_PRODUCT, MAX_STATES

from .frontend import CONTRACT, goal, read_source, target_value
from .semantics import cell, evaluate, initial, model, valid_state

SCHEMA = "qkf-signed-word-predicate-certificate-v1"
SOURCE_SCHEMA = "qkf-signed-word-predicate-source-v1"


def check_source(source, spec, cert):
    require(type(cert) is dict and set(cert) == {"schema", "ir", "carrier", "observations"}
            and cert["schema"] == SOURCE_SCHEMA, "signed predicate source fields")
    ir = read_source(source, spec["entry"], spec["word_type"])
    require(digest(ir) == digest(cert["ir"]), "exact signed predicate source binding")
    records = cert["carrier"]
    require(type(records) is list and 0 < len(records) <= MAX_STATES,
            "signed source carrier budget")
    states = []
    for i, row in enumerate(records):
        require(type(row) is dict and set(row) == {"state", "parent"},
                "signed source record fields")
        state = valid_state(ir, row["state"])
        require(state not in states, "distinct signed source states")
        parent = row["parent"]
        if i == 0:
            require(parent is None and state == initial(ir), "signed source initial state")
        else:
            require(type(parent) is list and len(parent) == 2
                    and integer(parent[0], 0, i - 1)
                    and parent[1] in {"0", "1"}, "signed source parent")
            require(cell(ir, states[parent[0]], parent[1]) == state,
                    "signed source reachability")
        states.append(state)

    data = model(ir, states)
    checked = check_observations(data, cert["observations"])
    obs = cert["observations"]
    table = {(row["state"], row["symbol"]): row["next"] for row in obs["cells"]}
    terminals = {
        q: data["terminal"][block[0]] == "true"
        for q, block in enumerate(obs["blocks"])
    }
    return ir, checked, table, terminals, (obs["initial"], 0, 0)


def joint_step(table, limit, state, symbol):
    require(type(symbol) is str and symbol in {"0", "1"}, "binary signed predicate column")
    bit = int(symbol)
    return table[state[0], symbol], min(limit, state[1] + bit), bit


def prepare(source, spec, source_cert):
    limit = goal(spec)
    return (limit, *check_source(source, spec, source_cert))


def check(source, spec, cert):
    require(type(cert) is dict and set(cert) == {"schema", "goal_sha256", "source", "proof"}
            and cert["schema"] == SCHEMA, "signed predicate certificate fields")
    require(cert["goal_sha256"] == digest(spec), "signed predicate goal binding")
    limit, ir, checked, table, terminals, start = prepare(source, spec, cert["source"])
    native_width = 32 if spec["word_type"] == "int" else 64
    base = {
        "contract": CONTRACT,
        "entry": spec["entry"],
        "word_type": spec["word_type"],
        "java_width": native_width,
        "goal_sha256": digest(spec),
        "source_sha256": ir["source_sha256"],
        "source": checked,
        "trust": (
            "restricted annotated unary frontend; modular cuts, equality, signed-zero "
            "terminal atoms and count/sign target rules; not Lean-verified"
        ),
    }
    proof = cert["proof"]
    require(type(proof) is dict and proof.get("kind") in {"closure", "counterexample"},
            "signed predicate proof")

    if proof["kind"] == "closure":
        require(set(proof) == {"kind", "states"}, "positive signed predicate proof fields")
        rows, states = proof["states"], []
        require(type(rows) is list and 0 < len(rows) <= MAX_PRODUCT,
                "signed predicate product budget")
        for i, row in enumerate(rows):
            require(type(row) is dict and set(row) == {"state", "parent"},
                    "signed predicate product record")
            raw = row["state"]
            require(type(raw) is list and len(raw) == 3
                    and integer(raw[0], 0, checked["classes"] - 1)
                    and integer(raw[1], 0, limit)
                    and integer(raw[2], 0, 1),
                    "typed count/sign/source product")
            state = tuple(raw)
            require(state not in states, "distinct signed predicate product states")
            parent = row["parent"]
            if i == 0:
                require(parent is None and state == start, "signed predicate product initial")
            else:
                require(type(parent) is list and len(parent) == 2
                        and integer(parent[0], 0, i - 1),
                        "earlier signed product parent")
                require(joint_step(table, limit, states[parent[0]], parent[1]) == state,
                        "signed product reachability")
            states.append(state)

        known = set(states)
        for state in states:
            for symbol in ("0", "1"):
                following = joint_step(table, limit, state, symbol)
                require(following in known, "signed predicate product closure")
                require(
                    terminals[following[0]]
                    == target_value(spec["target"], following[1], following[2]),
                    "violated signed terminal predicate obligation",
                )
        return {
            **base,
            "status": "certified",
            "all_positive_widths": True,
            "product_states": len(states),
            "checked_edges": 2 * len(states),
        }

    require(set(proof) == {"kind", "bits", "input", "output", "expected"},
            "signed predicate witness fields")
    bits = proof["bits"]
    require(type(bits) is str and 0 < len(bits) <= 4096 and set(bits) <= {"0", "1"},
            "positive signed witness width")
    width = len(bits)
    x = sum(int(bit) << i for i, bit in enumerate(bits))
    q = start[0]
    for symbol in bits:
        q = table[q, symbol]
    actual = evaluate(ir, x, width)
    expected = target_value(spec["target"], x.bit_count(), int(bits[-1]))
    require(actual == terminals[q], "signed whole-word evaluation and terminal factor agree")
    require(integer(proof["input"], 0, (1 << width) - 1)
            and type(proof["output"]) is bool and type(proof["expected"]) is bool,
            "typed signed Boolean witness")
    require((proof["input"], proof["output"], proof["expected"]) == (x, actual, expected)
            and actual != expected, "actual signed predicate target violation")

    native_x = x & ((1 << native_width) - 1)
    native_sign = (native_x >> (native_width - 1)) & 1
    native_actual = evaluate(ir, native_x, native_width)
    native_expected = target_value(spec["target"], native_x.bit_count(), native_sign)
    return {
        **base,
        "status": "refuted",
        "all_positive_widths": False,
        "width": width,
        "input": x,
        "output": actual,
        "expected": expected,
        "native_width_check": {
            "input": native_x,
            "output": native_actual,
            "expected": native_expected,
            "violates_goal": native_actual != native_expected,
            "kind": "IR evaluation, not Java execution",
        },
    }
