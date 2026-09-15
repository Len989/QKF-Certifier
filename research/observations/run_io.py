"""Bounded UTF-8/JSON I/O for the common research interface.

Packages embed their proofs; replay never follows package-supplied paths.
Inputs are never overwritten. A failed/partial JSON write cannot be replayed
as an acceptance. Limits here bound transport, not the mathematical word width.
"""
import json
from pathlib import Path

from .run_package import RunError

MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_SPEC_BYTES = 64 * 1024
MAX_PACKAGE_BYTES = 32 * 1024 * 1024


def _read(path, limit, status):
    path = Path(path)
    try:
        if not path.is_file():
            raise OSError("regular input file required: " + str(path))
        with path.open("rb") as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("input exceeds byte limit: " + str(path))
        return raw.decode("utf-8")
    except (OSError, ValueError) as exc:
        # An unreadable file is an input error, even when its role is package.
        error_status = "input_error" if isinstance(exc, OSError) else status
        raise RunError(error_status, "input_io", str(exc)) from exc


def read_source(path):
    return _read(path, MAX_SOURCE_BYTES, "input_error")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _constant(value):
    raise ValueError("non-finite JSON constant: " + value)


def read_json(path, *, package=False):
    status = "invalid_certificate" if package else "input_error"
    text = _read(path, MAX_PACKAGE_BYTES if package else MAX_SPEC_BYTES, status)
    try:
        return json.loads(text, object_pairs_hook=_object, parse_constant=_constant)
    except (ValueError, TypeError, RecursionError) as exc:
        raise RunError(status, "json", str(exc)) from exc


def new_path(path):
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise RunError("input_error", "output", "output already exists: " + str(path))
    return path


def write_json(path, value):
    try:
        raw = (json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        with Path(path).open("xb") as output:
            output.write(raw)
    except OSError as exc:
        raise RunError("input_error", "output", str(exc)) from exc


def write_run(directory, result, package):
    """Reserve a NEW directory; only complete target results get package.json."""
    path = new_path(directory)
    try:
        path.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise RunError("input_error", "output", str(exc)) from exc
    if package is not None:
        write_json(path / "package.json", package)
    write_json(path / "result.json", result)
