"""Reproduce local package timings; no external solver or service is invoked."""

import json
import platform
import statistics
import time
from pathlib import Path

from qkf_certifier import __version__, check_certificate, verify


def main():
    root = Path(__file__).resolve().parents[1]
    rows = []
    for name in ("and", "or", "xor"):
        sources = {
            "program": (root / "examples/ntmy" / f"{name}.mlir").read_bytes().decode("utf-8")
        }
        if name == "xor":
            sources["meet"] = (root / "examples/ntmy/meet.mlir").read_bytes().decode("utf-8")
        result = verify(sources, name)
        assert result["status"] == "certified"
        timings = {}
        for label, function in [
            ("verify", lambda: verify(sources, name)),
            ("check", lambda: check_certificate(sources, name, result["certificate"])),
        ]:
            samples = []
            for _ in range(31):
                start = time.perf_counter()
                checked = function()
                samples.append((time.perf_counter() - start) * 1000)
                assert checked["status"] == "certified"
            timings[label + "_median_ms"] = statistics.median(samples)
        rows.append({"target": name, "steps": result["rewrite_steps"], **timings})
    print(
        json.dumps(
            {
                "version": __version__,
                "python": platform.python_version(),
                "platform": platform.platform(),
                "scope": "31 repetitions; warm caches; parsing included; verify includes generation and replay; check replays a ready certificate; not an end-to-end synthesis benchmark",
                "results": rows,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
