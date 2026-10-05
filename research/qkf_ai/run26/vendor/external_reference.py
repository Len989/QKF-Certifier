"""Independent SQLite-method reference for Run25, not a third-party product.

No qkf_import implementation is imported.  Compatibility is limited to the
published id/value CSV effect and receipt-v1 contract.  Standard UPSERT, TEMP
tables and an explicit transaction provide the execution machinery.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

VERSION = "qkf.import.csv.v1"
RECEIPT = "qkf.import.receipt.v1"
BATCH_SIZE = 1024
FIELD_LIMIT = 131072
_IDS = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_VALUES = re.compile(r"(?:0|[1-9][0-9]{0,6})\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_COUNT_NAMES = frozenset(("input_rows", "invalid_rows", "duplicate_valid_rows", "valid_ids", "existing_ids", "inserted_ids", "before_rows", "after_rows"))
_FIELDS = frozenset(("schema", "format_version", "operation_key", "payload_sha256", "payload_fingerprint", "canonical_input_sha256", "before_sha256", "after_sha256", "counts", "goal_verified"))


class ReferenceError(Exception):
    pass


class InputFormatError(ReferenceError):
    pass


class KeyConflict(ReferenceError):
    pass


class SchemaError(ReferenceError):
    pass


class IntegrityError(ReferenceError):
    pass


class UnknownOperation(ReferenceError):
    pass


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _key(key):
    if not isinstance(key, str) or not 1 <= len(key) <= 256 or "\0" in key:
        raise ValueError("operation key must contain 1..256 characters and no NUL")


def _fingerprint(payload):
    return _sha(VERSION + "\0" + payload)


def _schema(connection, create):
    if create:
        connection.execute("CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY,value TEXT NOT NULL)")
        connection.execute("CREATE TABLE IF NOT EXISTS qkf_import_receipts(operation_key TEXT PRIMARY KEY NOT NULL,format_version TEXT NOT NULL,payload_sha256 TEXT NOT NULL,payload_fingerprint TEXT NOT NULL,receipt_json TEXT NOT NULL,receipt_sha256 TEXT NOT NULL)")
    specifications = {
        "items": (("id", "TEXT", None, 1), ("value", "TEXT", 1, 0)),
        "qkf_import_receipts": (("operation_key", "TEXT", 1, 1), ("format_version", "TEXT", 1, 0), ("payload_sha256", "TEXT", 1, 0), ("payload_fingerprint", "TEXT", 1, 0), ("receipt_json", "TEXT", 1, 0), ("receipt_sha256", "TEXT", 1, 0)),
    }
    for table, required in specifications.items():
        columns = connection.execute(f'PRAGMA table_xinfo("{table}")').fetchall()
        if len(columns) != len(required):
            raise SchemaError(f"incompatible {table} columns")
        for column, (name, typ, nonnull, primary) in zip(columns, required):
            if column[1] != name or column[2].upper() != typ or (nonnull is not None and column[3] != nonnull) or column[5] != primary or column[6] != 0:
                raise SchemaError(f"incompatible {table} column {name}")
        primary_indices = [i for i in connection.execute(f'PRAGMA index_list("{table}")') if i[3] == "pk"]
        if len(primary_indices) != 1:
            raise SchemaError(f"missing binary primary key in {table}")
        escaped = primary_indices[0][1].replace('"', '""')
        key_columns = [i for i in connection.execute(f'PRAGMA index_xinfo("{escaped}")') if i[5] == 1]
        if len(key_columns) != 1 or key_columns[0][2] != required[0][0] or key_columns[0][4] != "BINARY":
            raise SchemaError(f"non-binary primary key in {table}")
    if connection.execute("SELECT 1 FROM sqlite_schema WHERE type='trigger' AND tbl_name IN ('items','qkf_import_receipts') LIMIT 1").fetchone():
        raise SchemaError("managed-table triggers are unsupported")
    if connection.execute("SELECT 1 FROM items WHERE typeof(id)!='text' OR typeof(value)!='text' LIMIT 1").fetchone():
        raise SchemaError("old items must have text identifiers and values")


def _rows_digest(connection, table):
    digest = hashlib.sha256(b"[")
    count = 0
    for identifier, value in connection.execute(f"SELECT id,value FROM {table} ORDER BY id COLLATE BINARY"):
        if count:
            digest.update(b",")
        digest.update(_encode({"id": identifier, "value": value}).encode("utf-8"))
        count += 1
    digest.update(b"]")
    return count, digest.hexdigest()


def _stored(connection, key):
    row = connection.execute("SELECT format_version,payload_sha256,payload_fingerprint,receipt_json,receipt_sha256 FROM qkf_import_receipts WHERE operation_key=?", (key,)).fetchone()
    if row is None:
        return None
    version, payload, fingerprint, serialized, checksum = row
    try:
        receipt = json.loads(serialized)
        if not isinstance(receipt, dict) or set(receipt) != _FIELDS or _encode(receipt) != serialized or _sha(serialized) != checksum:
            raise ValueError("noncanonical or damaged receipt")
        if version != VERSION or receipt["format_version"] != version or receipt["schema"] != RECEIPT or receipt["operation_key"] != key or receipt["payload_sha256"] != payload or receipt["payload_fingerprint"] != fingerprint or fingerprint != _fingerprint(payload) or receipt["goal_verified"] is not True:
            raise ValueError("receipt metadata mismatch")
        for field in ("payload_sha256", "payload_fingerprint", "canonical_input_sha256", "before_sha256", "after_sha256"):
            if not isinstance(receipt[field], str) or not _DIGEST.fullmatch(receipt[field]):
                raise ValueError("invalid digest")
        counts = receipt["counts"]
        if not isinstance(counts, dict) or set(counts) != _COUNT_NAMES or any(type(v) is not int or v < 0 for v in counts.values()):
            raise ValueError("invalid counts")
        if counts["input_rows"] != counts["invalid_rows"] + counts["duplicate_valid_rows"] + counts["valid_ids"] or counts["valid_ids"] != counts["existing_ids"] + counts["inserted_ids"] or counts["after_rows"] != counts["before_rows"] + counts["inserted_ids"] or counts["existing_ids"] > counts["before_rows"]:
            raise ValueError("count relations fail")
        empty = hashlib.sha256(b"[]").hexdigest()
        for count, field in (("valid_ids", "canonical_input_sha256"), ("before_rows", "before_sha256"), ("after_rows", "after_sha256")):
            if counts[count] == 0 and receipt[field] != empty:
                raise ValueError("empty digest mismatch")
        if counts["inserted_ids"] == 0 and receipt["before_sha256"] != receipt["after_sha256"]:
            raise ValueError("no-insert state changed")
    except (ValueError, TypeError, KeyError) as error:
        raise IntegrityError("stored receipt failed independent validation") from error
    return receipt


class _HashingReader(io.RawIOBase):
    def __init__(self, binary):
        super().__init__()
        self.binary = binary
        self.digest = hashlib.sha256()

    def readable(self):
        return True

    def readinto(self, buffer):
        length = self.binary.readinto(buffer)
        if length:
            self.digest.update(memoryview(buffer)[:length])
        return length


def _stage(connection, binary, expected_payload):
    connection.execute("CREATE TEMP TABLE reference_stage(id TEXT PRIMARY KEY,value TEXT NOT NULL)")
    counts = {"input_rows": 0, "invalid_rows": 0, "duplicate_valid_rows": 0}
    eligible = 0
    batch = []
    reader = _HashingReader(binary)
    text = io.TextIOWrapper(io.BufferedReader(reader), encoding="utf-8", errors="strict", newline="")
    csv.field_size_limit(FIELD_LIMIT)

    def flush():
        if batch:
            connection.executemany("INSERT INTO reference_stage(id,value) VALUES(?,?) ON CONFLICT(id) DO NOTHING", batch)
            batch.clear()

    try:
        rows = csv.reader(text, strict=True)
        if next(rows, None) != ["id", "value"]:
            raise InputFormatError("CSV header must be exactly id,value")
        for row in rows:
            counts["input_rows"] += 1
            if len(row) != 2:
                raise InputFormatError("every CSV record must contain exactly two fields")
            identifier, value = row
            if not _IDS.fullmatch(identifier) or not _VALUES.fullmatch(value) or int(value) > 1000000:
                counts["invalid_rows"] += 1
                continue
            eligible += 1
            batch.append((identifier, value))
            if len(batch) == BATCH_SIZE:
                flush()
        flush()
    except (UnicodeError, csv.Error) as error:
        raise InputFormatError("CSV encoding or structure is invalid") from error
    finally:
        text.close()
    if reader.digest.hexdigest() != expected_payload:
        raise InputFormatError("CSV bytes changed between hash and parser pass")
    valid, digest = _rows_digest(connection, "reference_stage")
    counts["valid_ids"] = valid
    counts["duplicate_valid_rows"] = eligible - valid
    return counts, digest


class ClassicImporter:
    """Run25 reference: bounded Python batching and a verified SQLite UPSERT."""
    def __init__(self, db_path, timeout=30.0):
        self.db_path = Path(db_path)
        self.timeout = timeout

    def _connection(self):
        connection = sqlite3.connect(self.db_path, timeout=self.timeout, isolation_level=None)
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA temp_store=FILE")
        return connection

    def initialize(self):
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            _schema(connection, True)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def import_csv(self, csv_path, operation_key, fault=None):
        _key(operation_key)
        notify = fault or (lambda point: None)
        replay = False
        with open(csv_path, "rb") as binary:
            digest = hashlib.sha256()
            while block := binary.read(65536):
                digest.update(block)
            payload = digest.hexdigest()
            binary.seek(0)
            connection = self._connection()
            try:
                connection.execute("BEGIN IMMEDIATE")
                _schema(connection, True)
                previous = _stored(connection, operation_key)
                if previous is not None:
                    if previous["payload_fingerprint"] != _fingerprint(payload):
                        raise KeyConflict("operation key already binds different CSV bytes")
                    receipt = previous
                    replay = True
                else:
                    notify("after_begin")
                    counts, canonical_input = _stage(connection, binary, payload)
                    connection.execute("CREATE TEMP TABLE reference_before(id TEXT PRIMARY KEY,value TEXT NOT NULL)")
                    connection.execute("INSERT INTO reference_before SELECT id,value FROM items")
                    before_rows, before_digest = _rows_digest(connection, "reference_before")
                    existing = connection.execute("SELECT count(*) FROM reference_stage JOIN reference_before USING(id)").fetchone()[0]
                    notify("after_stage")
                    connection.execute("INSERT INTO items(id,value) SELECT id,value FROM reference_stage WHERE true ON CONFLICT(id) DO NOTHING")
                    notify("after_effect")
                    expected = "SELECT id,value FROM reference_before UNION ALL SELECT s.id,s.value FROM reference_stage AS s WHERE NOT EXISTS(SELECT 1 FROM reference_before AS b WHERE b.id=s.id)"
                    missing = connection.execute(f"WITH expected AS ({expected}) SELECT 1 FROM (SELECT id,value FROM expected EXCEPT SELECT id,value FROM items) LIMIT 1").fetchone()
                    extra = connection.execute(f"WITH expected AS ({expected}) SELECT 1 FROM (SELECT id,value FROM items EXCEPT SELECT id,value FROM expected) LIMIT 1").fetchone()
                    if missing is not None or extra is not None:
                        raise IntegrityError("full postcondition differs from protected before-state plus new IDs")
                    after_rows, after_digest = _rows_digest(connection, "items")
                    inserted = counts["valid_ids"] - existing
                    if after_rows != before_rows + inserted:
                        raise IntegrityError("postcondition row count differs")
                    counts.update(existing_ids=existing, inserted_ids=inserted, before_rows=before_rows, after_rows=after_rows)
                    receipt = dict(schema=RECEIPT, format_version=VERSION, operation_key=operation_key, payload_sha256=payload, payload_fingerprint=_fingerprint(payload), canonical_input_sha256=canonical_input, before_sha256=before_digest, after_sha256=after_digest, counts=counts, goal_verified=True)
                    serialized = _encode(receipt)
                    connection.execute("INSERT INTO qkf_import_receipts VALUES(?,?,?,?,?,?)", (operation_key, VERSION, payload, _fingerprint(payload), serialized, _sha(serialized)))
                    notify("after_receipt")
                    notify("before_commit")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.close()
        if not replay:
            notify("after_commit")
        return receipt

    def get_receipt(self, operation_key):
        _key(operation_key)
        if not self.db_path.exists():
            return None
        connection = sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=rw", uri=True, timeout=self.timeout, isolation_level=None)
        try:
            connection.execute("BEGIN")
            if not connection.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name='qkf_import_receipts'").fetchone():
                return None
            _schema(connection, False)
            return _stored(connection, operation_key)
        finally:
            connection.rollback()
            connection.close()

    def export_receipt(self, operation_key, output_path, fault=None):
        destination = Path(output_path)
        same_file = destination.resolve() == self.db_path.resolve()
        if destination.exists() and self.db_path.exists():
            same_file = same_file or os.path.samefile(destination, self.db_path)
        if same_file:
            raise ValueError("receipt output cannot replace its database")
        receipt = self.get_receipt(operation_key)
        if receipt is None:
            raise UnknownOperation(operation_key)
        notify = fault or (lambda point: None)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", prefix=".reference-receipt-", dir=destination.parent, delete=False) as stream:
                temporary = stream.name
                stream.write((_encode(receipt) + "\n").encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            notify("after_export_write")
            notify("before_export_replace")
            os.replace(temporary, destination)
            temporary = None
            notify("after_export_replace")
            directory = os.open(destination.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
        return receipt
