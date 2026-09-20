"""Small strict JSON boundary, without importing legacy proof routes."""
import json
from pathlib import Path

MAX_JSON = 5_000_000
MAX_SOURCE = 2_000_000


def freeze(value):
    """Snapshot plain JSON as immutable text; reject coerced keys/types and cycles."""
    active = set()
    def visit(obj):
        typ = type(obj)
        if typ in (str, bool, int, float, type(None)):
            return
        if typ not in (dict, list) or id(obj) in active:
            raise ValueError("acyclic plain JSON values required")
        active.add(id(obj))
        if typ is dict:
            if any(type(k) is not str for k in obj):
                raise ValueError("JSON object keys must be strings")
            for v in obj.values(): visit(v)
        else:
            for v in obj: visit(v)
        active.remove(id(obj))
    visit(value)
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(text.encode()) > MAX_JSON:
        raise ValueError("JSON byte budget")
    return text


def thaw(text):
    return json.loads(text)


def load_json(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_JSON: raise ValueError("JSON byte budget")
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out: raise ValueError("duplicate JSON key: " + key)
            out[key] = value
        return out
    def nonfinite(value): raise ValueError("nonfinite JSON number: " + value)
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite)


def save_json(path, value):
    # Validate before opening; never truncate an existing output.
    text = freeze(value)
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text + "\n")


def source_text(value):
    if type(value) is not str or len(value.encode("utf-8")) > MAX_SOURCE:
        raise ValueError("bounded source text required")
    return value
