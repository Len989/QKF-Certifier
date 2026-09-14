"""Produce a source-bound minimal factor and inspectable merge explanations."""
import itertools
import json
import sys
from pathlib import Path

from .context_factor import Runner, check, consumer_model, explain
from .descending_adapter import native_model, pinned_model
from .factor_producer import synthesize
from .model import require
from .run_context_experiment import decode_word, integer_pass


def validate_integer_loop(data, cert, *, max_width=5, strict=False):
    runner = Runner(data, cert)
    context = cert["context"]
    old_cells = {(c["state"], c["symbol"]): c["next"] for c in context["cells"]}
    counts = []
    for width in range(1, max_width + 1):
        cases = accepted = 0
        for word in itertools.product(data["alphabet"], repeat=width):
            answer = runner.run(word)["accepted"]
            old = context["initial"]
            for a in word:
                old = old_cells[old, a]
            inputs = decode_word(word)
            actual = integer_pass(inputs["base"], inputs["optional"], inputs["upper"], width, strict=strict)
            require(answer == context["states"][old]["accept"] == (inputs["proposed"] == actual),
                    "factor/residual/integer mismatch")
            accepted += answer
            cases += 1
        counts.append({"width": width, "cases": cases, "accepted": accepted, "mismatches": 0})
    return {"cases": sum(r["cases"] for r in counts), "mismatches": 0, "by_width": counts,
            "scope": "bounded unsigned check; all-continuation factor correctness is certified separately"}


def main():
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=False)
    source = (Path(__file__).resolve().parents[1] / "graal/previous/row_kernel.py").read_text()
    original = pinned_model()
    cases = {"descending": (original, None, False),
             "strict_guard": (native_model(source, ["and", ["optional"], ["comparison", [-1]]]), None, True),
             "all_contexts": (original, original["contexts"], False)}
    results = {}
    for name, (data, queries, strict) in cases.items():
        p = synthesize(data, queries=queries)
        require(p["status"] == "candidate", "factor experiment budget")
        cert = p["certificate"]
        result = check(data, cert)
        result["integer_validation"] = validate_integer_loop(data, cert, strict=strict)
        result["blocks"] = cert["factor"]["blocks"]
        result["pullbacks_attempted"] = p["pullbacks"]
        result["old_context_loss_witness_rejected"] = not Runner(data, cert).run(cert["context"]["gap"]["word"])["accepted"]
        for suffix, value in [("model", data), ("certificate", cert), ("explanation", explain(data, cert)),
                              ("consumer", consumer_model(data, cert["context"], cert["consumer_queries"]))]:
            (output / f"{name}.{suffix}.json").write_text(json.dumps(value, indent=2) + "\n")
        results[name] = result
    results["insufficient_class_budget"] = synthesize(original, max_classes=9)
    (output / "RESULTS.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps({name: {k: v for k, v in result.items() if k in {
        "status", "residual_states", "classes", "derived_questions", "max_separator_length",
        "full_context_recoverable", "reason", "integer_validation"}} for name, result in results.items()}, indent=2))


if __name__ == "__main__":
    main()
