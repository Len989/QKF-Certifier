"""Derive shared-cut evidence and compare with a direct unsigned integer loop."""
import itertools
import json
import sys
from pathlib import Path

from .context_checker import check
from .context_model import ContextModel
from .context_producer import synthesize
from .descending_adapter import native_model, pinned_model
from .model import require


def decode_word(word):
    values = [sum(int(column[j]) << i for i, column in enumerate(word)) for j in range(4)]
    return dict(zip(("base", "optional", "upper", "proposed"), values))


def integer_pass(base, optional, upper, width, *, strict=False):
    """Direct high-to-low loop, with no comparison-state or residual machinery."""
    y = base
    for bit in reversed(range(width)):
        trial = y | (1 << bit)
        if optional & (1 << bit) and (trial < upper if strict else trial <= upper):
            y = trial
    return y


def validate_integer_loop(data, cert, *, max_width=5, strict=False):
    check(data, cert)
    m = ContextModel(data)
    cells = {(r["state"], r["symbol"]): r["next"] for r in cert["cells"]}
    tables = {(r["control"], r["symbol"]): r["table"] for r in cert["rows"]}
    counts = []
    for width in range(1, max_width + 1):
        cases = accepted = weak_only = 0
        for word in itertools.product(m.alphabet, repeat=width):
            state, c, weak = cert["initial"], m.initial, m.bottom
            for a in word:
                state = cells[state, a]
                weak = tables[c, a][m.top if weak else 0]
                c = m.rows[c, a][0]
            inputs = decode_word(word)
            actual = integer_pass(inputs["base"], inputs["optional"], inputs["upper"], width, strict=strict)
            exact = cert["states"][state]["accept"]
            require(exact == (inputs["proposed"] == actual), "integer loop mismatch")
            independent = bool(weak & (1 << m.index[m.boundary]))
            require(not exact or independent, "erasure unexpectedly excludes an exact trace")
            cases += 1
            accepted += exact
            weak_only += independent and not exact
        counts.append({"width": width, "cases": cases, "exact_accepts": accepted,
                       "erasure_false_accepts": weak_only, "mismatches": 0})
    return {"cases": sum(r["cases"] for r in counts), "mismatches": 0, "by_width": counts,
            "scope": f"exhaustive legal unsigned columns, widths 1..{max_width}; not an all-width source proof"}


def main():
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=False)
    source = (Path(__file__).resolve().parents[1] / "graal/previous/row_kernel.py").read_text()
    cases = {"descending": (pinned_model(), False),
             "strict_guard": (native_model(source, ["and", ["optional"], ["comparison", [-1]]]), True)}
    results = {}
    for name, (data, strict) in cases.items():
        proposal = synthesize(data)
        require(proposal["status"] == "candidate", "context experiment budget")
        cert = proposal["certificate"]
        result = check(data, cert)
        result["integer_validation"] = validate_integer_loop(data, cert, strict=strict)
        result["product_states_visited"] = proposal["product_states_visited"]
        if cert["gap"]:
            word = cert["gap"]["word"]
            inputs = decode_word(word)
            result["counterexample"] = {"width": len(word), **inputs, "word_low_to_high": word,
                "actual": integer_pass(inputs["base"], inputs["optional"], inputs["upper"], len(word), strict=strict),
                "conflict": cert["gap"]["conflict"]}
        results[name] = result
        for suffix, value in [("model", data), ("certificate", cert)]:
            (output / f"{name}.{suffix}.json").write_text(json.dumps(value, indent=2) + "\n")
    results["insufficient_state_budget"] = synthesize(cases["descending"][0], max_states=1)
    results["insufficient_search_budget"] = synthesize(cases["descending"][0], max_product=1)
    (output / "RESULTS.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
