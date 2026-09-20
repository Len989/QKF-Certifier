"""Explain an already checked factor; no re-synthesis or separator search.

Question words are recovered from their earlier-parent derivations. Split
classes are distinguished by checked continuation witnesses. Merges are justified
by protected terminal labels and local stability, not by finite sample agreement.
"""
from research.observations.model import require
from .checker import CONSUMER, rebuild


def explain(source, selection, certificate):
    _, model, _ = rebuild(source, selection, certificate)
    proof, bridge = certificate["observations"], certificate["source_model"]
    questions = []
    for i, p in enumerate(proof["predicates"]):
        kind = p["kind"]
        if kind == "pullback":
            parent = questions[p["parent"]]
            word, terminal, label = [p["symbol"]] + parent["word_lsb"], parent["terminal"], parent["label"]
        else:
            word, terminal, label = ([] if kind == "terminal" else [p["symbol"]]), kind == "terminal", p["label"]
        # Re-evaluate the explanation itself against all model states. This
        # checks the order of continuation bits rather than trusting a label.
        for state in model.states:
            trace, end = model.run(state, word)
            value = model.terminal[end] if terminal else trace[-1]
            require((value == label) == bool(p["mask"] & (1 << model.index[state])),
                    "question explanation does not match its checked mask")
        questions.append({"id": i, "kind": kind, "parent": p.get("parent"),
                          "word_lsb": word, "terminal": terminal, "label": label,
                          "mask": p["mask"], "meaning": ("source terminal after continuation equals label"
                          if terminal else "source output at last continuation step equals label")})
    prefixes = []
    for row in bridge["carrier"]:
        parent = row["parent"]
        prefixes.append([] if parent is None else prefixes[parent[0]] + [parent[1]])
    histories = {"q%03d" % i: word for i, word in enumerate(prefixes)}
    block_of = {state: i for i, block in enumerate(proof["blocks"]) for state in block}
    classes = []
    for i, block in enumerate(proof["blocks"]):
        representative = block[0]
        classes.append({"id": i, "members": block, "terminal": model.terminal[representative],
                        "signature": [bool(p["mask"] & (1 << model.index[representative])) for p in proof["predicates"]],
                        "reachability_prefixes_lsb": {s: histories[s] for s in block},
                        "stability": [{"symbol": a, "output": model.step[representative, a][0],
                                       "next_class": block_of[model.step[representative, a][1]],
                                       "checked_representatives": len(block)} for a in model.alphabet]})
    separators = [{**row,
                   "left_prefix_lsb": histories[proof["blocks"][row["left"]][0]],
                   "right_prefix_lsb": histories[proof["blocks"][row["right"]][0]]}
                  for row in proof["separators"]]
    return {"schema": "qkf-signed-observation-explanation-v1", "consumer": CONSUMER,
            "model_sha256": model.sha256, "questions": questions, "classes": classes,
            "separators": separators, "target_checked": False,
            "scope": "checked source behavior, not target counterexamples or Paper II proof-depth minima"}
