"""Bounded, read-only file observations; no SQLite recovery or directory edits."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import sqlite3
import struct
import sys
import time


def _stat(value):
    return {"st_dev": value.st_dev, "st_ino": value.st_ino,
            "size": value.st_size, "mtime_ns": value.st_mtime_ns,
            "ctime_ns": value.st_ctime_ns, "mode": value.st_mode}


def _error(error):
    return {"type": type(error).__name__, "message": str(error),
            "errno": getattr(error, "errno", None)}


def file_snapshot(path):
    """Record path and FD identities, bytes, and both post-read identities."""
    path = Path(path)
    result = {"path": str(path), "exists": None}
    try:
        result["lstat_before"] = _stat(path.lstat())
        result["exists"] = True
        with path.open("rb") as stream:
            result["fd_stat_before"] = _stat(os.fstat(stream.fileno()))
            header = stream.read(128)
            digest = hashlib.sha256(header)
            count = len(header)
            while block := stream.read(65536):
                digest.update(block)
                count += len(block)
            result.update(sha256=digest.hexdigest(), bytes_read=count,
                          header_hex=header.hex(),
                          fd_stat_after=_stat(os.fstat(stream.fileno())))
        result["lstat_after"] = _stat(path.lstat())
        result["stable_during_read"] = (
            result["lstat_before"] == result["fd_stat_before"] ==
            result["fd_stat_after"] == result["lstat_after"])
        if path.name.endswith("-journal") and len(header) >= 28:
            result["journal_header"] = {
                "magic_hex": header[:8].hex(),
                "n_records": struct.unpack(">I", header[8:12])[0],
                "initial_database_pages": struct.unpack(">I", header[16:20])[0],
                "sector_size": struct.unpack(">I", header[20:24])[0],
                "page_size": struct.unpack(">I", header[24:28])[0],
            }
    except FileNotFoundError as error:
        result["exists"] = False if "lstat_before" not in result else True
        result["error"] = _error(error)
    except Exception as error:
        result["error"] = _error(error)
    return result


def snapshot(db):
    db = Path(db).absolute()
    result = {"db": str(db), "files": {
        suffix or "database": file_snapshot(str(db) + suffix)
        for suffix in ("", "-journal", "-wal", "-shm")}}
    try:
        result["directory"] = {
            "path": str(db.parent), "stat": _stat(db.parent.stat()),
            "entries": sorted(os.listdir(db.parent)),
        }
    except Exception as error:
        result["directory"] = {"path": str(db.parent), "error": _error(error)}
    return result


def environment(db=None):
    db = Path(db).absolute() if db is not None else Path.cwd() / "database.sqlite"
    result = {"python": sys.version, "executable": sys.executable,
              "sqlite_version": sqlite3.sqlite_version,
              "platform": platform.platform(), "cwd": str(Path.cwd()),
              "db": str(db), "pid": os.getpid(), "ppid": os.getppid(),
              "proc_available": Path("/proc/self/status").exists(),
              "environment": {key: os.environ[key] for key in (
                  "GITHUB_ACTIONS", "RUNNER_OS", "RUNNER_ARCH", "RUNNER_ENVIRONMENT",
                  "PYTHONHASHSEED", "TMPDIR", "TEMP", "TMP") if key in os.environ}}
    try:
        value = os.statvfs(db.parent)
        result["statvfs"] = {key: getattr(value, key) for key in (
            "f_bsize", "f_frsize", "f_blocks", "f_bfree", "f_bavail", "f_files",
            "f_ffree", "f_favail", "f_flag", "f_namemax")}
    except Exception as error:
        result["statvfs_error"] = _error(error)
    return result


def connection_settings(connection):
    settings = {}
    for pragma in ("journal_mode", "synchronous", "cache_size", "cache_spill",
                   "temp_store", "page_size", "locking_mode"):
        try:
            settings[pragma] = connection.execute(f"PRAGMA {pragma}").fetchone()[0]
        except Exception as error:
            settings[pragma] = {"error": _error(error)}
    return settings


class Observer:
    def __init__(self, trace, db):
        self.trace = Path(trace)
        self.db = Path(db).absolute()
        self.sequence = 0
        # The runner creates the parent and ensures this is a fresh attempt.
        self.stream = self.trace.open("x", encoding="utf-8", newline="\n")

    def emit(self, event, *, observe=True, **extra):
        self.sequence += 1
        record = {"schema": "qkf.run26.observation.v1", "seq": self.sequence,
                  "event": event, "time_ns": time.time_ns(),
                  "monotonic_ns": time.monotonic_ns(), "pid": os.getpid(), **extra}
        if observe:
            record["snapshot"] = snapshot(self.db)
        record["observation_finished_monotonic_ns"] = time.monotonic_ns()
        self.stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")) + "\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())
        return record

    def close(self):
        self.stream.close()
