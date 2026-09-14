"""Independent bridge from checked shared cuts to a checked consumer factor."""
from .checker import check as check_observations
from .context_checker import check as check_context
from .context_model import ContextModel
from .model import ATOMIC_CERT_SCHEMA, MAX_STATES, MODEL_SCHEMA, Model, digest, require

SCHEMA = "qkf-context-consumer-factor-v1"


def consumer_model(data, context_certificate, queries=None):
    """Rebuild the finite consumer model from a validated residual certificate."""
    check_context(data, context_certificate)
    m = ContextModel(data)
    queries = [m.boundary] if queries is None else queries
    require(type(queries) is list and queries and all(type(q) is str and q in m.contexts for q in queries)
            and len(queries) == len(set(queries)) and m.boundary in queries,
            "consumer queries must retain the declared boundary")
    queries = sorted(queries)
    states = context_certificate["states"]
    require(len(states) <= MAX_STATES, "consumer model native-state budget")
    labels = [f"s{i:02d}" for i in range(len(states))]
    return Model({"schema": MODEL_SCHEMA, "states": labels, "alphabet": m.alphabet,
                  "initial": labels[context_certificate["initial"]], "outputs": ["tick"],
                  "terminal": {labels[i]: "".join(
                      "1" if state["allowed"] & (1 << m.index[q]) else "0" for q in queries)
                      for i, state in enumerate(states)},
                  "steps": [{"state": labels[c["state"]], "symbol": c["symbol"],
                             "output": "tick", "next": labels[c["next"]]}
                            for c in context_certificate["cells"]],
                  "binding": {"adapter": "checked-context-residual-v1", "context_model_sha256": m.sha256,
                              "context_certificate_sha256": digest(context_certificate),
                              "consumer_queries": queries}}).data


def _check(data, cert):
    require(type(cert) is dict and set(cert) == {
        "schema", "context_model_sha256", "consumer_queries", "context", "factor"
    }, "context factor certificate fields")
    native = ContextModel(data)
    require(cert["schema"] == SCHEMA and cert["context_model_sha256"] == native.sha256,
            "factor belongs to a different local context model")
    model = Model(consumer_model(data, cert["context"], cert["consumer_queries"]))
    require(cert["consumer_queries"] == model.binding["consumer_queries"], "canonical consumer queries")
    require(type(cert["factor"]) is dict and cert["factor"].get("schema") == ATOMIC_CERT_SCHEMA,
            "context factor uses atomic completion")
    factor_result = check_observations(model.data, cert["factor"])
    return native, model, factor_result


def check(data, cert):
    native, model, result = _check(data, cert)
    blocks = cert["factor"]["blocks"]
    states = {f"s{i:02d}": s for i, s in enumerate(cert["context"]["states"])}
    recoverable = all(len({states[s]["allowed"] for s in b}) == 1 for b in blocks)
    return {"status": "certified", "residual_states": len(model.states), "classes": len(blocks),
            "removed_states": len(model.states) - len(blocks),
            "merged_pairs": sum(len(b) * (len(b) - 1) // 2 for b in blocks),
            "separated_class_pairs": len(blocks) * (len(blocks) - 1) // 2,
            "derived_questions": result["derived_observations"], "max_separator_length": result["max_witness_length"],
            "row_templates": result["row_templates"], "stored_native_cells": result["supplied_cells"],
            "stored_forced_steps": 0, "logical_forced_cells": result["forced_cells"],
            "transitions": len(cert["factor"]["cells"]), "consumer_queries": model.binding["consumer_queries"],
            "full_context_recoverable": recoverable,
            "minimality": "coarsest stable factor preserving declared consumer answers for every finite continuation",
            "scope": "the independently checked finite context model; no new all-width Java or Lean theorem"}


def explain(data, cert):
    """Derive human-inspectable merge obligations from independently checked data."""
    native, model, _ = _check(data, cert)
    factor = cert["factor"]
    states = {f"s{i:02d}": s for i, s in enumerate(cert["context"]["states"])}
    class_of = {s: i for i, block in enumerate(factor["blocks"]) for s in block}
    questions = []
    for p in factor["predicates"]:
        if p["kind"] == "terminal":
            questions.append({"word": [], "terminal_label": p["label"]})
        elif p["kind"] == "pullback":
            old = questions[p["parent"]]
            questions.append({**old, "word": [p["symbol"]] + old["word"]})
        else:
            # A constant tick question is legal but contributes no distinction.
            questions.append({"word": [p["symbol"]], "output_label": p["label"]})
    classes = []
    for i, block in enumerate(factor["blocks"]):
        s = block[0]
        masks = {states[t]["allowed"] for t in block}
        classes.append({"class": i, "members": [
            {"state": t, "control": states[t]["control"], "allowed": native.members(states[t]["allowed"])}
            for t in block], "terminal": model.terminal[s],
            "question_answers": [bool(p["mask"] & (1 << model.index[s])) for p in factor["predicates"]],
            "recovered_contexts": native.members(next(iter(masks))) if len(masks) == 1 else None})
    merges = []
    for block in factor["blocks"]:
        for i, s in enumerate(block):
            for t in block[i + 1:]:
                merges.append({"left": s, "right": t, "terminal": model.terminal[s], "obligations": [
                    {"symbol": a, "left_next": model.step[s, a][1], "right_next": model.step[t, a][1],
                     "shared_next_class": class_of[model.step[s, a][1]]} for a in model.alphabet]})
    return {"consumer_queries": model.binding["consumer_queries"], "questions": questions, "classes": classes,
            "merges": merges, "separators": factor["separators"],
            "merge_justification": "same terminal answers and successor classes for every symbol; induction covers all continuations"}


class Runner:
    """Validate once; execute the factor without retaining residual control/masks."""
    def __init__(self, data, cert):
        native, model, _ = _check(data, cert)
        factor = cert["factor"]
        self.initial = factor["initial"]
        self.queries = model.binding["consumer_queries"]
        self.boundary = native.boundary
        self.cells = {(c["state"], c["symbol"]): c["next"] for c in factor["cells"]}
        self.terminal = [model.terminal[b[0]] for b in factor["blocks"]]
        self.alphabet = set(model.alphabet)

    def run(self, word):
        require(type(word) in {list, tuple} and all(type(a) is str and a in self.alphabet for a in word),
                "factor runner symbols")
        state = self.initial
        for a in word:
            state = self.cells[state, a]
        answers = {q: bit == "1" for q, bit in zip(self.queries, self.terminal[state])}
        return {"class": state, "accepted": answers[self.boundary], "answers": answers}
