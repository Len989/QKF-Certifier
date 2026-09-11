from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def bundle():
    def load(name):
        sources = {
            "program": (ROOT / "examples/ntmy" / f"{name}.mlir").read_bytes().decode("utf-8")
        }
        if name == "xor":
            sources["meet"] = (ROOT / "examples/ntmy/meet.mlir").read_bytes().decode("utf-8")
        return sources

    return load
