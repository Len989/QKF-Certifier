"""Propose a closed successor observation or a shortest discovered refutation.

The checker does not import this search. Budget exhaustion never produces a
certificate or an acceptance claim. The caller already supplies the source
certificate and the independent target; this search cannot change either.
"""
from .model import integer, require
from .successor_kernel import MAX_STATES, MAX_WITNESS, SCHEMA, System
from .successor_spec import decode


def synthesize(source, source_certificate, spec, *, max_states=MAX_STATES,
               max_witness=MAX_WITNESS):
    require(integer(max_states, 1, MAX_STATES) and integer(max_witness, 1, MAX_WITNESS),
            "successor producer budgets")
    system = System(source, source_certificate, spec)
    states = [system.initial]
    nodes = [{"state": list(system.initial), "parent": None}]
    index = {system.initial: 0}
    base = {"schema": SCHEMA, "binding": system.binding}

    def exhausted(reason):
        return {"status": "budget_exhausted", "stage": "successor_property",
                "reason": reason, "explored_states": len(states), "certificate": None}

    for i, state in enumerate(states):
        for column in system.alphabet:
            following = system.advance(state, column)
            reason = system.bad(following)
            if reason is not None:
                word = [column]
                ancestor = i
                while nodes[ancestor]["parent"] is not None:
                    ancestor, previous = nodes[ancestor]["parent"]
                    word.append(previous)
                word.reverse()
                if len(word) > max_witness:
                    return exhausted("counterexample length budget")
                _, outputs = system.trace(word)
                certificate = {**base, "kind": "counterexample", "word": word,
                               "values": decode(word, outputs), "reason": reason}
                return {"status": "candidate", "certificate": certificate}
            if following not in index:
                if len(states) == max_states:
                    return exhausted("joint observation state budget")
                index[following] = len(states)
                states.append(following)
                nodes.append({"state": list(following), "parent": [i, column]})
    return {"status": "candidate",
            "certificate": {**base, "kind": "closed_observation", "states": nodes}}
