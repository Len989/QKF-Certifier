"""Cold pair auditor: recover expendable copies and check an independent oracle.

This module intentionally imports neither any product nor fixture/writer code.
The observations supplied by the producer are not accepted as expected state.
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(65536):
            digest.update(block)
    return digest.hexdigest()


def _expected(n, mode):
    # Formula is maintained independently of the fixture generator.
    if mode == "normalized":
        for i in range(n * 4 // 10):
            yield f"b{i:09d}", str((i * 17 + 11) % 1000001)
    else:
        for i in range(n):
            yield f"b{i:09d}", f"legacy-{i % 97}"
    if mode != "before":
        for i in range(n * 4 // 10):
            yield f"n{i:09d}", str(((i + n * 4 // 10) * 17 + 11) % 1000001)


def _digest(rows):
    digest, count = hashlib.sha256(b"["), 0
    for key, value in rows:
        if count:
            digest.update(b",")
        digest.update(_json({"id": key, "value": value}).encode("utf-8"))
        count += 1
    digest.update(b"]")
    return count, digest.hexdigest()


def _oracle(fixture):
    n = fixture["n"]
    if type(n) is not int or n < 10 or n % 10:
        raise ValueError("invalid fixture scale")
    expected = {
        "before_sha": _digest(_expected(n, "before"))[1],
        "after_sha": _digest(_expected(n, "after"))[1],
        "canonical_input_sha": _digest(_expected(n, "normalized"))[1],
        "counts": {"input_rows": n, "invalid_rows": n // 10,
                   "duplicate_valid_rows": n // 10, "valid_ids": 8 * n // 10,
                   "existing_ids": 4 * n // 10, "inserted_ids": 4 * n // 10,
                   "before_rows": n, "after_rows": 14 * n // 10},
    }
    for field, value in expected.items():
        if fixture.get(field) != value:
            raise ValueError(f"fixture metadata disagrees with independent oracle: {field}")
    payload = Path(fixture["csv"])
    expected["payload_sha"] = _sha_file(payload)
    if expected["payload_sha"] != fixture.get("payload_sha"):
        raise ValueError("fixture payload hash differs")
    # Check every row of the independently generated source, not only its hash.
    def source_rows():
        yield from _expected(n, "normalized")
        for i in range(n // 10):
            yield f"!invalid{i:09d}", "7"
        for i in range(n // 10):
            yield f"b{i:09d}", str(((i + n) * 17 + 11) % 1000001)
    with payload.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        if next(reader, None) != ["id", "value"]:
            raise ValueError("fixture CSV header differs")
        marker = object()
        for actual, wanted in itertools.zip_longest(reader, source_rows(), fillvalue=marker):
            if actual is marker or wanted is marker or tuple(actual) != wanted:
                raise ValueError("fixture CSV row differs from independent oracle")
    return expected


def _match_rows(connection, n, mode):
    marker, mismatch, count = object(), [], 0
    rows = connection.execute("SELECT id,value FROM items ORDER BY id COLLATE BINARY")
    digest = hashlib.sha256(b"[")
    for actual, wanted in itertools.zip_longest(rows, _expected(n, mode), fillvalue=marker):
        if actual is not marker:
            if count:
                digest.update(b",")
            digest.update(_json({"id": actual[0], "value": actual[1]}).encode("utf-8"))
            count += 1
        if actual is marker or wanted is marker or actual != wanted:
            if len(mismatch) < 5:
                mismatch.append({"actual": None if actual is marker else list(actual),
                                 "expected": None if wanted is marker else list(wanted)})
    digest.update(b"]")
    return {"match": not mismatch, "rows": count, "sha256": digest.hexdigest(),
            "first_mismatches": mismatch}


def _schema(connection):
    expected_items = [("id", "TEXT", 0, 1), ("value", "TEXT", 1, 0)]
    expected_receipts = [("operation_key", "TEXT", 1, 1)] + [
        (name, "TEXT", 1, 0) for name in ("format_version", "payload_sha256",
                                         "payload_fingerprint", "receipt_json", "receipt_sha256")]
    for name, wanted in (("items", expected_items), ("qkf_import_receipts", expected_receipts)):
        columns = list(connection.execute(f'PRAGMA table_xinfo("{name}")'))
        if [(r[1], r[2].upper(), r[3], r[5]) for r in columns] != wanted or any(r[6] for r in columns):
            raise ValueError(f"{name} schema differs")
        indexes = [r for r in connection.execute(f'PRAGMA index_list("{name}")') if r[3] == "pk"]
        if len(indexes) != 1:
            raise ValueError(f"{name} primary key differs")
        parts = [r for r in connection.execute("SELECT * FROM pragma_index_xinfo(?)", (indexes[0][1],)) if r[5]]
        if len(parts) != 1 or parts[0][2] != wanted[0][0] or parts[0][4].upper() != "BINARY":
            raise ValueError(f"{name} primary key collation differs")
    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name IN ('items','qkf_import_receipts')").fetchone():
        raise ValueError("unexpected table trigger")
    if connection.execute("SELECT 1 FROM items WHERE typeof(id)!='text' OR typeof(value)!='text' LIMIT 1").fetchone():
        raise ValueError("item value has wrong storage type")


def _receipt(connection, key, backend, oracle):
    rows = list(connection.execute("SELECT operation_key,format_version,payload_sha256,payload_fingerprint,receipt_json,receipt_sha256 FROM qkf_import_receipts"))
    if len(rows) != 1:
        return {"valid": False, "count": len(rows), "error": "expected exactly one receipt"}
    operation, version, payload, fingerprint, encoded, checksum = rows[0]
    try:
        control = backend.startswith("minimal")
        expected_schema = "qkf.run26.control.v1" if control else "qkf.import.receipt.v1"
        expected_version = "qkf.run26.control.v1" if control else "qkf.import.csv.v1"
        expected_fingerprint = hashlib.sha256((expected_version + "\x00" + oracle["payload_sha"]).encode()).hexdigest()
        receipt = json.loads(encoded)
        wanted = {
            "schema": expected_schema, "format_version": expected_version,
            "operation_key": key, "payload_sha256": oracle["payload_sha"],
            "payload_fingerprint": expected_fingerprint,
            "canonical_input_sha256": oracle["canonical_input_sha"],
            "before_sha256": oracle["before_sha"], "after_sha256": oracle["after_sha"],
            "counts": oracle["counts"], "goal_verified": True,
        }
        if any(not isinstance(value, str) for value in rows[0]):
            raise ValueError("receipt columns must be TEXT")
        if (operation, version, payload, fingerprint) != (key, expected_version, oracle["payload_sha"], expected_fingerprint):
            raise ValueError("receipt row identity or binding differs")
        if not isinstance(receipt, dict) or set(receipt) != set(wanted) or receipt != wanted:
            raise ValueError("receipt content differs from independent oracle")
        if type(receipt["goal_verified"]) is not bool or not isinstance(receipt["counts"], dict):
            raise ValueError("receipt metadata type differs")
        if any(type(receipt["counts"][name]) is not int for name in wanted["counts"]):
            raise ValueError("receipt count must have exact integer type")
        if encoded != _json(receipt) or checksum != hashlib.sha256(encoded.encode("utf-8")).hexdigest():
            raise ValueError("receipt canonical encoding or checksum differs")
        return {"valid": True, "count": 1, "sha256": checksum, "schema": expected_schema}
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        return {"valid": False, "count": len(rows), "error": str(error)}


def audit_pair(pairdir: str | Path, spec: dict, fixture: dict) -> dict:
    """Validate closed observed bytes after normal recovery on a disposable copy."""
    root = Path(pairdir)
    database, journal = root / "database.sqlite", root / "database.sqlite-journal"
    result = {"pass": False, "state": "error", "integrity": None,
              "original_unchanged": False, "journal_present": journal.exists()}
    original = {}
    try:
        original = {path.name: _sha_file(path) for path in (database, journal) if path.exists()}
        if not database.is_file():
            raise ValueError("database.sqlite is missing")
        result["original_hashes"] = original
        oracle = _oracle(fixture)
        with tempfile.TemporaryDirectory(prefix="qkf26-cold-") as temporary:
            copy = Path(temporary) / "database.sqlite"
            shutil.copyfile(database, copy)
            if journal.exists():
                shutil.copyfile(journal, Path(temporary) / journal.name)
            connection = sqlite3.connect(copy)
            try:
                result["integrity"] = [r[0] for r in connection.execute("PRAGMA integrity_check")]
                if result["integrity"] != ["ok"]:
                    raise ValueError("SQLite integrity check failed")
                _schema(connection)
                pre = _match_rows(connection, fixture["n"], "before")
                post = _match_rows(connection, fixture["n"], "after")
                result["items"] = {"rows": post["rows"], "sha256": post["sha256"],
                                   "state": "PRE" if pre["match"] else "POST" if post["match"] else "MIXED"}
                count = connection.execute("SELECT count(*) FROM qkf_import_receipts").fetchone()[0]
                if pre["match"] and count == 0:
                    result.update(state="PRE", receipt={"count": 0, "valid": True})
                else:
                    receipt = _receipt(connection, spec.get("operation_key", "run26"), spec.get("backend", spec.get("engine", "minimal")), oracle)
                    result["receipt"] = receipt
                    result["state"] = "POST" if post["match"] and receipt["valid"] else "MIXED"
                result["pass"] = result["state"] in ("PRE", "POST")
                if result["state"] == "MIXED":
                    result["pre_mismatches"] = pre["first_mismatches"]
                    result["post_mismatches"] = post["first_mismatches"]
            finally:
                connection.close()
            result["recovered_sha256"] = _sha_file(copy)
            result["recovery_journal_present"] = Path(temporary, journal.name).exists()
    except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as error:
        result["error"] = f"{type(error).__name__}: {error}"
        # Immutable reads are diagnostic only and can never turn a failed audit PASS.
        if database.exists():
            try:
                connection = sqlite3.connect(database.resolve().as_uri() + "?immutable=1", uri=True)
                try:
                    result["immutable_diagnostic"] = {
                        "items": connection.execute("SELECT count(*) FROM items").fetchone()[0],
                        "receipts": connection.execute("SELECT count(*) FROM qkf_import_receipts").fetchone()[0],
                    }
                finally:
                    connection.close()
            except sqlite3.Error as diagnostic_error:
                result["immutable_diagnostic_error"] = str(diagnostic_error)
    finally:
        current = {path.name: _sha_file(path) for path in (database, journal) if path.exists()}
        result["original_unchanged"] = bool(original) and original == current
        if not result["original_unchanged"]:
            result["pass"] = False
            result["original_change_error"] = "observed original pair was changed or unavailable"
    return result
