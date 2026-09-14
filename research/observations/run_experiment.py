"""Produce small inspectable certificates and compare the distinct experiments."""
import json
import sys
from pathlib import Path

from .checker import check
from .producer import synthesize
from .source_adapter import PROGRAM, pinned_model, native_model
from .examples import delayed


def main():
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=False)
    source = (Path(__file__).resolve().parents[1] / "graal/carry_kernel.py").read_text()
    invisible = delayed()
    for row in invisible["steps"]:
        row["output"] = "0"
    cases = {"carry": pinned_model(),
             "changed_forbidden_action": native_model(source, {**PROGRAM, "forbidden_action": "clear"}),
             "delayed_observation": delayed(), "unobserved_internal_state": invisible}
    results = {}
    for name, data in cases.items():
        candidate = synthesize(data)
        if candidate["status"] != "candidate":
            raise RuntimeError(candidate)
        cert = candidate["certificate"]
        result = check(data, cert)
        results[name] = {**result, "pullbacks_attempted": candidate["pullbacks"],
                         "blocks": cert["blocks"], "separators": cert["separators"]}
        for suffix, value in [("model", data), ("certificate", cert)]:
            (output / f"{name}.{suffix}.json").write_text(json.dumps(value, indent=2) + "\n")
    results["insufficient_budget"] = synthesize(delayed(), max_observations=1)
    (output / "RESULTS.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps({name: {k: v for k, v in result.items() if k in {
        "status", "native_states", "classes", "derived_observations", "forced_cells", "max_witness_length"
    }} for name, result in results.items()}, indent=2))


if __name__ == "__main__":
    main()
