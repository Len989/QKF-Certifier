"""Contract and local projection to the unchanged finite observation Model.

A distinct initialization state has terminal label 'not-a-word'. After every
bit the state is eligible for signed termination. This also works when the
arithmetic/atom residual vector returns to its initial value at positive width.
No partition, observation questions, target or certificate-supplied code occurs.
"""
from research.observations.model import MODEL_SCHEMA, MAX_STATES, Model, digest, integer, require
from research.signed_predicates.frontend import CONTRACT, read_source
from research.signed_predicates import semantics as signed

REQUEST_SCHEMA = "qkf-signed-source-request-v1"
SCHEMA = "qkf-signed-source-model-v1"
COMPLETION = "positive-width-last-bit-sign-v1"
ALPHABET = ("0", "1")
EMPTY = "not-a-word"


class CapacityExceeded(ValueError):
    """A complete source model could not be produced within the stated budget."""


def request(entry, word_type):
    return {"schema": REQUEST_SCHEMA, "contract": CONTRACT,
            "entry": dict(entry), "word_type": word_type}


def read(source, selection):
    require(type(source) is str, "source text")
    require(type(selection) is dict and set(selection) == {
        "schema", "contract", "entry", "word_type"
    }, "source request fields; a target cannot be supplied here")
    require(selection["schema"] == REQUEST_SCHEMA and selection["contract"] == CONTRACT,
            "signed source request contract")
    # The retained parser validates class/method identifiers and the selected
    # overload; no method-name dispatch supplies semantics.
    return read_source(source, selection["entry"], selection["word_type"])


def binding(selection, ir):
    return {"source_sha256": ir["source_sha256"], "request_sha256": digest(selection),
            "source_ir_sha256": digest(ir), "contract": CONTRACT,
            "completion": COMPLETION}


def initial(ir):
    return False, signed.initial(ir)


def advance(ir, state, symbol):
    require(type(symbol) is str and symbol in ALPHABET, "binary bridge symbol")
    return True, signed.valid_state(ir, signed.cell(ir, state[1], symbol))


def state_value(ir, raw):
    require(type(raw) is dict and set(raw) == {"has_bits", "residual", "parent"},
            "source state record fields")
    require(type(raw["has_bits"]) is bool and type(raw["residual"]) is list,
            "typed completion flag and residual")
    return raw["has_bits"], signed.valid_state(ir, raw["residual"])


def finite_model(ir, selection, states):
    """Reconstruct *every* table cell from source semantics, never from JSON."""
    require(0 < len(states) <= MAX_STATES and len(set(states)) == len(states),
            "distinct bounded bridge carrier")
    names = {state: "q%03d" % i for i, state in enumerate(states)}
    require(initial(ir) in names, "bridge initial is covered")
    steps, terminal = [], {}
    for state, name in names.items():
        terminal[name] = str(bool(signed.terminal(ir, state[1]))).lower() if state[0] else EMPTY
        for symbol in ALPHABET:
            following = advance(ir, state, symbol)
            require(following in names, "incomplete bridge carrier: reachable successor omitted")
            steps.append({"state": name, "symbol": symbol, "output": "_",
                          "next": names[following]})
    return Model({"schema": MODEL_SCHEMA, "states": list(names.values()),
                  "alphabet": list(ALPHABET), "outputs": ["_"],
                  "initial": names[initial(ir)], "terminal": terminal,
                  "steps": steps, "binding": binding(selection, ir)})


def word_value(model, x, width):
    """Execute an already checked Model at a finite width (not a proof search).

This convenience evaluator is bounded to 4096 bits. The local simulation
certificate itself has no width parameter. No value is assigned to width zero.
"""
    require(isinstance(model, Model), "checked finite Model required")
    require(integer(width, 1, 4096) and integer(x, 0, (1 << width) - 1),
            "positive-width raw word")
    state = model.initial
    for position in range(width):
        output, state = model.step[state, str((x >> position) & 1)]
        require(output == "_", "bridge must not emit intermediate Boolean results")
    label = model.terminal[state]
    require(label in {"true", "false"}, "nonempty bridge terminal")
    return label == "true"
