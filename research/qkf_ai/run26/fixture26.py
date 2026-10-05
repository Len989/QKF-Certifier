"""Independent deterministic Run26 fixtures; no importer implementation imports."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sqlite3


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(65536):
            digest.update(block)
    return digest.hexdigest()


def _size(n: int) -> None:
    if type(n) is not int or n < 10 or n % 10:
        raise ValueError("n must be an integer >= 10 divisible by 10")


def _base_id(i: int) -> str:
    return f"b{i:09d}"


def _new_id(i: int) -> str:
    return f"n{i:09d}"


def _value(i: int) -> str:
    return str((17 * i + 11) % 1000001)


def before_rows(n: int):
    _size(n)
    for i in range(n):
        # Existing values deliberately lie outside the new CSV integer grammar.
        yield _base_id(i), f"legacy-{i % 97}"


def input_rows(n: int):
    _size(n)
    overlap = 4 * n // 10
    for i in range(overlap):
        yield _base_id(i), _value(i)
    for i in range(overlap):
        yield _new_id(i), _value(i + overlap)
    for i in range(n // 10):
        yield f"!invalid{i:09d}", "7"
    for i in range(n // 10):
        # The changed duplicate value tests that the first valid CSV row wins.
        yield _base_id(i), _value(i + n)


def normalized_rows(n: int):
    _size(n)
    overlap = 4 * n // 10
    for i in range(overlap):
        yield _base_id(i), _value(i)
    for i in range(overlap):
        yield _new_id(i), _value(i + overlap)


def after_rows(n: int):
    yield from before_rows(n)
    for i in range(4 * n // 10):
        yield _new_id(i), _value(i + 4 * n // 10)


def rows_sha(rows) -> tuple[int, str]:
    digest = hashlib.sha256(b"[")
    count = 0
    for identifier, value in rows:
        if count:
            digest.update(b",")
        digest.update(canonical({"id": identifier, "value": value}).encode("utf-8"))
        count += 1
    digest.update(b"]")
    return count, digest.hexdigest()


def expectations(n: int) -> dict:
    _size(n)
    return {
        "n": n,
        "before_sha": rows_sha(before_rows(n))[1],
        "after_sha": rows_sha(after_rows(n))[1],
        "canonical_input_sha": rows_sha(normalized_rows(n))[1],
        "counts": {
            "input_rows": n,
            "invalid_rows": n // 10,
            "duplicate_valid_rows": n // 10,
            "valid_ids": 8 * n // 10,
            "existing_ids": 4 * n // 10,
            "inserted_ids": 4 * n // 10,
            "before_rows": n,
            "after_rows": 14 * n // 10,
        },
    }


def prepare(root: str | Path, n: int) -> dict:
    """Create a closed initial DB and exact UTF-8 CSV; refuse to overwrite either."""
    _size(n)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    database, payload = root / "initial.sqlite", root / "input.csv"
    if database.exists() or payload.exists():
        raise FileExistsError("fixture output already exists")
    with payload.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("id", "value"))
        writer.writerows(input_rows(n))
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("CREATE TABLE items(id TEXT PRIMARY KEY,value TEXT NOT NULL)")
        connection.execute("""CREATE TABLE qkf_import_receipts(
            operation_key TEXT PRIMARY KEY NOT NULL,
            format_version TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL,
            payload_fingerprint TEXT NOT NULL,
            receipt_json TEXT NOT NULL,
            receipt_sha256 TEXT NOT NULL)""")
        connection.executemany("INSERT INTO items VALUES(?,?)", before_rows(n))
        connection.commit()
    finally:
        connection.close()
    result = expectations(n)
    result.update(db=str(database.resolve()), csv=str(payload.resolve()),
                  payload_sha=file_sha(payload), initial_db_sha=file_sha(database))
    return result
