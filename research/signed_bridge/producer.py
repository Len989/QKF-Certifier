"""Propose the exact bounded reachable residual carrier, not an observation set."""
from research.observations.model import integer, require
from .model import (ALPHABET, MAX_STATES, SCHEMA, CapacityExceeded, advance,
                    binding, finite_model, initial, read)


def derive(source, selection, *, max_states=MAX_STATES):
    require(integer(max_states, 1, MAX_STATES), "bridge model budget must be 1..64")
    ir = read(source, selection)
    states = [initial(ir)]
    known = {states[0]}
    records = [{"has_bits": False, "residual": list(states[0][1]), "parent": None}]
    for i, state in enumerate(states):
        for symbol in ALPHABET:
            following = advance(ir, state, symbol)
            if following not in known:
                if len(states) >= max_states:
                    raise CapacityExceeded("bridge reachable-state budget (including initialization)")
                known.add(following)
                states.append(following)
                records.append({"has_bits": True, "residual": list(following[1]),
                                "parent": [i, symbol]})
    model = finite_model(ir, selection, states)
    certificate = {"schema": SCHEMA, "binding": binding(selection, ir), "ir": ir,
                   "carrier": records, "model": model.data}
    from .checker import check
    return certificate, check(source, selection, certificate)
