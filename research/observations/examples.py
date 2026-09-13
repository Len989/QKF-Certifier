"""A finite example whose required observation is not visible in one cell."""
from .model import MODEL_SCHEMA


def delayed():
    states = [str(i) for i in range(4)]
    return {"schema": MODEL_SCHEMA, "states": states, "alphabet": ["advance", "probe"],
            "outputs": ["0", "1"], "initial": "0", "terminal": {s: "" for s in states},
            "binding": {"example": "delayed distinction"}, "steps": [
                {"state": s, "symbol": a, "output": str(int(a == "probe" and s == "3")),
                 "next": str((int(s) + 1) % 4) if a == "advance" else s}
                for s in states for a in ["advance", "probe"]]}
