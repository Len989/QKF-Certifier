"""Independent product replay, with no discovery imports or target substitution."""
from copy import deepcopy

from research.observations.model import digest, integer, require
from research.signed_runtime.runtime import load
from .common import MAX_PRODUCT, MAX_WITNESS, Monitor, SCHEMA, binding, prepare, result


def check_product(monitor, proof):
    """Verify all supplied reachable states and every binary successor, not a sample."""
    require(type(proof) is dict and set(proof) == {"kind", "states"}
            and proof["kind"] == "closure", "row target closure fields")
    records = proof["states"]
    require(type(records) is list and 0 < len(records) <= MAX_PRODUCT, "product certificate size")
    states, seen = [], set()
    for i, row in enumerate(records):
        require(type(row) is dict and set(row) == {"state", "parent"}
                and monitor.valid(row["state"]), "typed product state record")
        state, parent = tuple(row["state"]), row["parent"]
        require(state not in seen, "duplicate product state")
        if i == 0:
            require(parent is None and state == monitor.initial, "product initial state")
        else:
            require(type(parent) is list and len(parent) == 2
                    and integer(parent[0], 0, i - 1), "strictly earlier product parent")
            require(monitor.step(states[parent[0]], parent[1]) == state, "product reachability")
        states.append(state)
        seen.add(state)
    for state in states:
        for symbol in monitor.alphabet:
            following = monitor.step(state, symbol)
            require(following in seen, "incomplete target product")
            require(not monitor.bad(following), "source does not satisfy independent target")
    return {"status": "certified", "product_states": len(states),
            "checked_transitions": len(states) * 2,
            "obligation": "source Boolean equals independent target after every nonempty word",
            "java_width": 32 if monitor.spec["word_type"] == "int" else 64}


def check_witness(source, selection, monitor, proof):
    require(type(proof) is dict and set(proof) == {"kind", "word"}
            and proof["kind"] == "counterexample", "row target counterexample fields")
    word = proof["word"]
    require(type(word) is list and 0 < len(word) <= MAX_WITNESS
            and all(type(c) is str and c in monitor.alphabet for c in word),
            "bounded nonempty counterexample word")
    state = monitor.initial
    for symbol in word:
        state = monitor.step(state, symbol)
    require(monitor.bad(state), "counterexample must fail at its final width")
    # Independent whole-word execution validates the concrete refutation; it is
    # not used by positive product transitions or by runtime execution.
    from research.signed_bridge.model import read
    from research.signed_predicates.semantics import evaluate
    from research.signed_predicates.frontend import target_value
    ir = read(source, selection)
    width = len(word)
    raw = sum(int(bit) << i for i, bit in enumerate(word))
    actual = evaluate(ir, raw, width)
    expected = target_value(monitor.spec["target"], raw.bit_count(), int(word[-1]))
    require(type(actual) is bool and actual == monitor.actual(state)
            and expected == monitor.expected(state) and actual != expected,
            "whole-word source/row/target witness agreement")
    native_width = 32 if selection["word_type"] == "int" else 64
    mask = (1 << native_width) - 1
    candidates = list(dict.fromkeys((raw & mask, 0, 1, 1 << (native_width - 1),
                                    (1 << (native_width - 1)) - 1, mask)))
    native = []
    for x in candidates:
        y = evaluate(ir, x, native_width)
        require(y == monitor.runner.value(x, native_width), "native-width IR/row agreement")
        e = target_value(monitor.spec["target"], x.bit_count(), x >> (native_width - 1))
        if y != e:
            native.append({"input": x, "output": y, "expected": e})
    return {"status": "refuted", "word_lsb_first": word, "witness_width": width,
            "input": raw, "output": actual, "expected": expected,
            "java_width": native_width, "native_width_witnesses": native,
            "native_validation": "finite whole-word IR/row checks, not Java execution or a width-lifting theorem"}


def check(source, target, certificate):
    target, certificate = deepcopy(target), deepcopy(certificate)
    compiled, selection = prepare(target)
    require(type(certificate) is dict and set(certificate) == {
        "schema", "binding", "observations", "obligation"
    } and certificate["schema"] == SCHEMA, "signed row target certificate fields")
    runner, receipt = load(source, selection, certificate["observations"])
    require(digest(certificate["binding"]) == digest(binding(compiled, receipt)),
            "source/target/observation/row-action binding")
    monitor = Monitor(runner, compiled["specification"])
    proof = certificate["obligation"]
    require(type(proof) is dict and proof.get("kind") in {"closure", "counterexample"},
            "signed row target obligation kind")
    checked = (check_product(monitor, proof) if proof["kind"] == "closure"
               else check_witness(source, selection, monitor, proof))
    return result(compiled, receipt, checked)
