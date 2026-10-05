"""A single SQLite transaction is the durable boundary for effects and receipts."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Callable, BinaryIO, Any

FORMAT_VERSION = "qkf.import.csv.v1"
RECEIPT_SCHEMA = "qkf.import.receipt.v1"
CSV_FIELD_LIMIT = 131072
ENGINES = ("ordinary", "staged")
FAULT_POINTS = (
    "after_begin", "after_stage", "after_effect", "after_receipt",
    "before_commit", "after_commit",
)
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_INTEGER = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_RECEIPTS = "qkf_import_receipts"


class QKFImportError(Exception):
    """Base class for errors in the importer contract."""


class InputFormatError(QKFImportError):
    """The CSV cannot be structurally parsed, decoded, or read consistently."""


class KeyConflict(QKFImportError):
    """An operation key already names another payload or format version."""


class SchemaError(QKFImportError):
    """The existing SQLite schema does not support this importer contract."""


class IntegrityError(QKFImportError):
    """A goal or durable receipt failed verification."""


class UnknownOperation(QKFImportError):
    """No committed receipt exists for this operation key."""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _key(key: str) -> None:
    if not isinstance(key, str) or not key or len(key) > 256 or "\x00" in key:
        raise ValueError("operation_key must be a nonempty string of at most 256 characters without NUL")


def _payload_hash(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    while block := stream.read(1024 * 1024):
        digest.update(block)
    return digest.hexdigest()


class _HashingReader(io.RawIOBase):
    """Hash precisely the bytes consumed by the UTF-8 CSV reader."""

    def __init__(self, stream: BinaryIO):
        super().__init__()
        self.stream = stream
        self.digest = hashlib.sha256()

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: bytearray) -> int:
        size = self.stream.readinto(buffer)
        if size:
            self.digest.update(memoryview(buffer)[:size])
        return size


def _row_digest(connection: sqlite3.Connection, table: str) -> tuple[int, str]:
    # Stream the canonical JSON array so hashing never materializes the rowset.
    digest = hashlib.sha256(b"[")
    count = 0
    for identifier, value in connection.execute(f'SELECT id,value FROM "{table}" ORDER BY id COLLATE BINARY'):
        if count:
            digest.update(b",")
        digest.update(_json({"id": identifier, "value": value}).encode("utf-8"))
        count += 1
    digest.update(b"]")
    return count, digest.hexdigest()


def _columns(connection: sqlite3.Connection, table: str) -> list[tuple]:
    return list(connection.execute(f'PRAGMA table_xinfo("{table}")'))


def _binary_primary_key(connection: sqlite3.Connection, table: str, name: str) -> bool:
    indexes = [row for row in connection.execute(f'PRAGMA index_list("{table}")') if row[3] == "pk"]
    if len(indexes) != 1:
        return False
    # Names from SQLite are bound through a pragma table function, never interpolated.
    columns = [row for row in connection.execute("SELECT * FROM pragma_index_xinfo(?)", (indexes[0][1],)) if row[5]]
    return len(columns) == 1 and columns[0][2] == name and columns[0][4].upper() == "BINARY"


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute("CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY,value TEXT NOT NULL)")
    columns = _columns(connection, "items")
    if (len(columns) != 2 or [(r[1], r[2].upper(), r[5]) for r in columns] !=
            [("id", "TEXT", 1), ("value", "TEXT", 0)] or columns[1][3] != 1
            or any(r[6] for r in columns) or not _binary_primary_key(connection, "items", "id")):
        raise SchemaError("items must have columns id TEXT PRIMARY KEY,value TEXT NOT NULL")
    if connection.execute("SELECT 1 FROM items WHERE typeof(id)!='text' OR typeof(value)!='text' LIMIT 1").fetchone():
        raise SchemaError("existing items must have non-NULL text IDs and text values")
    connection.execute(f"""CREATE TABLE IF NOT EXISTS {_RECEIPTS}(
        operation_key TEXT PRIMARY KEY NOT NULL,
        format_version TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL,
        payload_fingerprint TEXT NOT NULL,
        receipt_json TEXT NOT NULL,
        receipt_sha256 TEXT NOT NULL
    )""")
    expected = [
        ("operation_key", "TEXT", 1, 1), ("format_version", "TEXT", 1, 0),
        ("payload_sha256", "TEXT", 1, 0), ("payload_fingerprint", "TEXT", 1, 0),
        ("receipt_json", "TEXT", 1, 0), ("receipt_sha256", "TEXT", 1, 0),
    ]
    receipt_columns = _columns(connection, _RECEIPTS)
    if ([(r[1], r[2].upper(), r[3], r[5]) for r in receipt_columns] != expected
            or any(r[6] for r in receipt_columns)
            or not _binary_primary_key(connection, _RECEIPTS, "operation_key")):
        raise SchemaError("qkf_import_receipts has an incompatible schema")
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name IN (?,?) LIMIT 1",
        ("items", _RECEIPTS),
    ).fetchone():
        raise SchemaError("triggers on items or qkf_import_receipts are not supported")


def _read_receipt(connection: sqlite3.Connection, key: str) -> dict | None:
    row = connection.execute(
        f"SELECT format_version,payload_sha256,payload_fingerprint,receipt_json,receipt_sha256 "
        f"FROM {_RECEIPTS} WHERE operation_key=?", (key,),
    ).fetchone()
    if row is None:
        return None
    version, payload, fingerprint, encoded, receipt_hash = row
    try:
        receipt = json.loads(encoded)
        fields = {"schema", "format_version", "operation_key", "payload_sha256", "payload_fingerprint",
                  "canonical_input_sha256", "before_sha256", "after_sha256", "counts", "goal_verified"}
        if (not isinstance(receipt, dict) or set(receipt) != fields
                or _json(receipt) != encoded or _sha(encoded) != receipt_hash
                or receipt["schema"] != RECEIPT_SCHEMA or version != FORMAT_VERSION or receipt["format_version"] != version
                or receipt["operation_key"] != key or receipt["payload_sha256"] != payload
                or receipt["payload_fingerprint"] != fingerprint
                or fingerprint != _sha(version + "\x00" + payload)
                or receipt["goal_verified"] is not True):
            raise ValueError("receipt mismatch")
        for name in ("payload_sha256", "payload_fingerprint", "canonical_input_sha256", "before_sha256", "after_sha256"):
            if not isinstance(receipt[name], str) or not re.fullmatch(r"[0-9a-f]{64}", receipt[name]):
                raise ValueError("invalid receipt digest")
        counts = receipt["counts"]
        names = {"input_rows", "invalid_rows", "duplicate_valid_rows", "valid_ids", "existing_ids", "inserted_ids", "before_rows", "after_rows"}
        if (not isinstance(counts, dict) or set(counts) != names
                or any(type(value) is not int or value < 0 for value in counts.values())
                or counts["input_rows"] != counts["invalid_rows"] + counts["duplicate_valid_rows"] + counts["valid_ids"]
                or counts["valid_ids"] != counts["existing_ids"] + counts["inserted_ids"]
                or counts["after_rows"] != counts["before_rows"] + counts["inserted_ids"]
                or counts["existing_ids"] > counts["before_rows"]):
            raise ValueError("invalid receipt counts")
        empty = _sha("[]")
        if ((counts["valid_ids"] == 0 and receipt["canonical_input_sha256"] != empty)
                or (counts["before_rows"] == 0 and receipt["before_sha256"] != empty)
                or (counts["after_rows"] == 0 and receipt["after_sha256"] != empty)
                or (counts["inserted_ids"] == 0 and receipt["before_sha256"] != receipt["after_sha256"])):
            raise ValueError("invalid empty or unchanged-rowset digest")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise IntegrityError("stored receipt failed verification") from error
    return receipt


def _stage(connection: sqlite3.Connection, stream: BinaryIO, expected_sha: str) -> tuple[dict, str]:
    connection.execute("CREATE TEMP TABLE qkf_stage(id TEXT PRIMARY KEY,value TEXT NOT NULL)")
    counts = {"input_rows": 0, "invalid_rows": 0, "duplicate_valid_rows": 0}
    hashing = _HashingReader(stream)
    buffered = io.BufferedReader(hashing)
    text = io.TextIOWrapper(buffered, encoding="utf-8", errors="strict", newline="")
    try:
        csv.field_size_limit(CSV_FIELD_LIMIT)
        reader = csv.reader(text, strict=True)
        if next(reader, None) != ["id", "value"]:
            raise InputFormatError("CSV header must be exactly id,value in that order")
        for row in reader:
            if len(row) != 2:
                raise InputFormatError("every CSV record must have exactly two columns")
            counts["input_rows"] += 1
            identifier, value = row
            if (not _ID.fullmatch(identifier) or not _INTEGER.fullmatch(value)
                    or len(value) > 7 or int(value) > 1_000_000):
                counts["invalid_rows"] += 1
                continue
            changed = connection.execute(
                "INSERT OR IGNORE INTO qkf_stage(id,value) VALUES(?,?)", (identifier, value),
            ).rowcount
            if not changed:
                counts["duplicate_valid_rows"] += 1
        actual_sha = hashing.digest.hexdigest()
        if actual_sha != expected_sha:
            raise InputFormatError("CSV bytes changed between hashing and parsing")
    except (csv.Error, UnicodeError, OSError) as error:
        raise InputFormatError(f"CSV cannot be parsed as strict UTF-8: {error}") from error
    finally:
        # Detach the wrapper: the caller owns the binary descriptor for both passes.
        text.detach()
        buffered.detach()
    counts["valid_ids"], canonical_sha = _row_digest(connection, "qkf_stage")
    return counts, canonical_sha


def _staged_effect(connection: sqlite3.Connection, counts: dict, notify: Callable[[str], None]) -> tuple[int, str, int, str, int]:
    connection.execute("CREATE TEMP TABLE qkf_before(id TEXT PRIMARY KEY,value TEXT NOT NULL)")
    connection.execute("INSERT INTO qkf_before SELECT id,value FROM items")
    before_rows, before_sha = _row_digest(connection, "qkf_before")
    existing = connection.execute(
        "SELECT count(*) FROM qkf_stage s JOIN items i ON i.id=s.id",
    ).fetchone()[0]
    expected_inserted = counts["valid_ids"] - existing
    connection.execute(
        "INSERT INTO items(id,value) SELECT s.id,s.value FROM qkf_stage s "
        "WHERE NOT EXISTS(SELECT 1 FROM items i WHERE i.id=s.id)",
    )
    notify("after_effect")
    after_rows, after_sha = _row_digest(connection, "items")
    old_mismatch = connection.execute(
        "SELECT 1 FROM qkf_before b LEFT JOIN items i ON i.id=b.id "
        "WHERE i.id IS NULL OR i.value COLLATE BINARY!=b.value COLLATE BINARY LIMIT 1",
    ).fetchone()
    new_mismatch = connection.execute(
        "SELECT 1 FROM qkf_stage s LEFT JOIN qkf_before b ON b.id=s.id "
        "LEFT JOIN items i ON i.id=s.id WHERE i.id IS NULL "
        "OR i.value COLLATE BINARY!=CASE WHEN b.id IS NOT NULL THEN b.value ELSE s.value END COLLATE BINARY LIMIT 1",
    ).fetchone()
    if old_mismatch or new_mismatch or after_rows != before_rows + expected_inserted:
        raise IntegrityError("import goal or preservation of existing rows failed")
    return before_rows, before_sha, after_rows, after_sha, existing


def _memory_stage(stream: BinaryIO, expected_sha: str) -> tuple[dict, str, dict[str, str]]:
    """Parse a byte snapshot in memory; return the first valid occurrence per ID."""
    payload = stream.read()
    if hashlib.sha256(payload).hexdigest() != expected_sha:
        raise InputFormatError("CSV bytes changed between hashing and parsing")
    rows: dict[str, str] = {}
    counts = {"input_rows": 0, "invalid_rows": 0, "duplicate_valid_rows": 0}
    try:
        csv.field_size_limit(CSV_FIELD_LIMIT)
        reader = csv.reader(io.StringIO(payload.decode("utf-8", errors="strict"), newline=""), strict=True)
        if next(reader, None) != ["id", "value"]:
            raise InputFormatError("CSV header must be exactly id,value in that order")
        for row in reader:
            if len(row) != 2:
                raise InputFormatError("every CSV record must have exactly two columns")
            counts["input_rows"] += 1
            identifier, value = row
            if (not _ID.fullmatch(identifier) or not _INTEGER.fullmatch(value)
                    or len(value) > 7 or int(value) > 1_000_000):
                counts["invalid_rows"] += 1
            elif identifier in rows:
                counts["duplicate_valid_rows"] += 1
            else:
                rows[identifier] = value
    except (csv.Error, UnicodeError, OSError) as error:
        raise InputFormatError(f"CSV cannot be parsed as strict UTF-8: {error}") from error
    counts["valid_ids"] = len(rows)
    return counts, _memory_row_digest(rows), rows


def _memory_row_digest(rows: dict[str, str]) -> str:
    return _sha(_json([{"id": key, "value": rows[key]} for key in sorted(rows)]))


def _read_items(connection: sqlite3.Connection) -> dict[str, str]:
    return dict(connection.execute("SELECT id,value FROM items"))


def _ordinary_effect(connection: sqlite3.Connection, rows: dict[str, str], notify: Callable[[str], None]) -> tuple[int, str, int, str, int]:
    """Simple full snapshots make the exact preservation check explicit."""
    before = _read_items(connection)
    connection.executemany("INSERT OR IGNORE INTO items(id,value) VALUES(?,?)", rows.items())
    notify("after_effect")
    after = _read_items(connection)
    expected = dict(before)
    for identifier, value in rows.items():
        expected.setdefault(identifier, value)
    if after != expected:
        raise IntegrityError("import goal or preservation of existing rows failed")
    existing = len(rows.keys() & before.keys())
    return len(before), _memory_row_digest(before), len(after), _memory_row_digest(after), existing


class SafeImporter:
    """Import valid first occurrences atomically; preserve every existing item.

    Each call opens and closes its own connection. Receipt exports are derivatives
    of the committed SQL receipt and do not participate in the transaction.
    """

    def __init__(self, db_path: str | os.PathLike, *, engine: str = "ordinary", timeout: float = 30.0):
        if engine not in ENGINES:
            raise ValueError("engine must be ordinary or staged")
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
            raise ValueError("timeout must be finite and nonnegative")
        self.db_path = Path(db_path)
        self.engine = engine
        self.timeout = timeout

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=self.timeout, isolation_level=None)
        try:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA temp_store=FILE")
            return connection
        except BaseException:
            connection.close()
            raise

    def initialize(self) -> None:
        """Create the tables if absent; preserve and validate existing data."""
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            _ensure_schema(connection)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def import_csv(
        self, csv_path: str | os.PathLike, operation_key: str,
        fault: Callable[[str], None] | None = None,
    ) -> dict:
        """Return the stable committed receipt; an identical replay does no import.

        ``fault`` is an optional test hook, called at the documented transaction
        boundaries. An exception before commit rolls back; after_commit runs only
        after the connection has committed and closed.
        """
        _key(operation_key)
        notify = fault or (lambda point: None)
        with open(csv_path, "rb") as stream:
            payload_sha = _payload_hash(stream)
            fingerprint = _sha(FORMAT_VERSION + "\x00" + payload_sha)
            stream.seek(0)
            connection = self._connect()
            committed = False
            replay = False
            try:
                connection.execute("BEGIN IMMEDIATE")
                _ensure_schema(connection)
                prior = _read_receipt(connection, operation_key)
                if prior is not None:
                    if prior["format_version"] != FORMAT_VERSION or prior["payload_fingerprint"] != fingerprint:
                        raise KeyConflict("operation_key already belongs to different CSV bytes or a different format")
                    receipt = prior
                    replay = True
                    connection.rollback()
                else:
                    notify("after_begin")
                    if self.engine == "staged":
                        counts, canonical_sha = _stage(connection, stream, payload_sha)
                        notify("after_stage")
                        before_rows, before_sha, after_rows, after_sha, existing = _staged_effect(connection, counts, notify)
                    else:
                        counts, canonical_sha, rows = _memory_stage(stream, payload_sha)
                        notify("after_stage")
                        before_rows, before_sha, after_rows, after_sha, existing = _ordinary_effect(connection, rows, notify)
                    expected_inserted = counts["valid_ids"] - existing
                    counts.update({
                        "existing_ids": existing, "inserted_ids": expected_inserted,
                        "before_rows": before_rows, "after_rows": after_rows,
                    })
                    receipt = {
                        "schema": RECEIPT_SCHEMA, "format_version": FORMAT_VERSION,
                        "operation_key": operation_key, "payload_sha256": payload_sha,
                        "payload_fingerprint": fingerprint, "canonical_input_sha256": canonical_sha,
                        "before_sha256": before_sha, "after_sha256": after_sha,
                        "counts": counts, "goal_verified": True,
                    }
                    encoded = _json(receipt)
                    connection.execute(
                        f"INSERT INTO {_RECEIPTS} VALUES(?,?,?,?,?,?)",
                        (operation_key, FORMAT_VERSION, payload_sha, fingerprint, encoded, _sha(encoded)),
                    )
                    notify("after_receipt")
                    notify("before_commit")
                    connection.commit()
                    committed = True
            except BaseException:
                if not committed:
                    connection.rollback()
                raise
            finally:
                connection.close()
        if not replay:
            notify("after_commit")
        return receipt

    def get_receipt(self, operation_key: str) -> dict | None:
        """Read and verify a committed receipt without creating a database."""
        _key(operation_key)
        if not self.db_path.exists():
            return None
        # mode=rw prohibits accidental creation and lets SQLite roll back a hot
        # journal before this read after a killed writer.
        connection = sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=rw", uri=True, timeout=self.timeout)
        try:
            if not connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (_RECEIPTS,),
            ).fetchone():
                return None
            return _read_receipt(connection, operation_key)
        finally:
            connection.close()

    def export_receipt(
        self, operation_key: str, output_path: str | os.PathLike,
        fault: Callable[[str], None] | None = None,
    ) -> dict:
        """Regenerate an atomic JSON export from the committed SQL receipt."""
        if _same_file(output_path, self.db_path):
            raise ValueError("receipt output must not replace the SQLite database")
        receipt = self.get_receipt(operation_key)
        if receipt is None:
            raise UnknownOperation(operation_key)
        _atomic_export(receipt, output_path, fault)
        return receipt


def _same_file(first: str | os.PathLike, second: str | os.PathLike) -> bool:
    left, right = Path(first), Path(second)
    if left.resolve() == right.resolve():
        return True
    try:
        return left.samefile(right)
    except FileNotFoundError:
        return False


def export_receipt(
    db_path: str | os.PathLike, operation_key: str, output_path: str | os.PathLike,
    fault: Callable[[str], None] | None = None,
) -> dict:
    """Regenerate an exported receipt from committed SQL truth."""
    return SafeImporter(db_path).export_receipt(operation_key, output_path, fault)


def _atomic_export(
    receipt: dict, output_path: str | os.PathLike,
    fault: Callable[[str], None] | None = None,
) -> None:
    """Write a derivative receipt using file fsync, replace, and directory fsync."""
    destination = Path(output_path)
    encoded = (_json(receipt) + "\n").encode("utf-8")
    temporary: str | None = None
    notify = fault or (lambda point: None)
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=".qkf-receipt-", dir=destination.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(encoded)
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
