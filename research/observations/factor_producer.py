"""Compose existing context discovery and consumer-question closure."""
from .context_checker import check as check_context
from .context_factor import SCHEMA, consumer_model
from .context_model import ContextModel
from .context_producer import synthesize as synthesize_context
from .model import MAX_STATES
from .producer import synthesize as synthesize_observations


def synthesize(data, *, context_certificate=None, queries=None, max_context_states=MAX_STATES,
               max_product=65536, max_observations=63, max_pullbacks=4096, max_classes=MAX_STATES,
               context_row_encoding="complete"):
    if context_certificate is None:
        p = synthesize_context(data, max_states=max_context_states, max_product=max_product,
                               row_encoding=context_row_encoding)
        if p["status"] != "candidate":
            return {**p, "stage": "context"}
        context_certificate = p["certificate"]
    check_context(data, context_certificate)
    if len(context_certificate["states"]) > MAX_STATES:
        return {"status": "budget_exhausted", "stage": "bridge", "reason": "consumer model native-state budget",
                "certificate": None}
    model = consumer_model(data, context_certificate, queries)
    p = synthesize_observations(model, row_encoding="atomic", max_observations=max_observations,
                               max_pullbacks=max_pullbacks, max_classes=max_classes)
    if p["status"] != "candidate":
        return {**p, "stage": "factor"}
    return {"status": "candidate", "certificate": {
        "schema": SCHEMA, "context_model_sha256": ContextModel(data).sha256,
        "consumer_queries": model["binding"]["consumer_queries"],
        "context": context_certificate, "factor": p["certificate"]},
        "classes": p["classes"], "observations": p["observations"], "pullbacks": p["pullbacks"]}
