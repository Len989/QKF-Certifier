"""Fresh-process writer with observations around the actual connection calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sqlite3
import sys
import time
import traceback

from observe26 import Observer, connection_settings, environment

PRESSURE_BYTES = 256 * 1024 * 1024


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def install_connection_observer(observer, kill_at):
    original = sqlite3.connect

    class ObservedConnection(sqlite3.Connection):
        def commit(self):
            observer.emit("before_commit", in_transaction=self.in_transaction,
                          settings=connection_settings(self))
            if kill_at == "before_commit":
                observer.emit("kill_requested", observe=False, at=kill_at)
                os.kill(os.getpid(), signal.SIGKILL)
            result = super().commit()
            observer.emit("after_commit", in_transaction=self.in_transaction,
                          call_returned=True)
            if kill_at == "after_commit":
                observer.emit("kill_requested", observe=False, at=kill_at)
                os.kill(os.getpid(), signal.SIGKILL)
            return result

        def close(self):
            observer.emit("before_close", in_transaction=self.in_transaction)
            result = super().close()
            observer.emit("after_close", call_returned=True)
            return result

    def connect(*args, **kwargs):
        if len(args) > 5:
            raise RuntimeError("instrumentation does not accept a positional factory")
        if "factory" in kwargs:
            raise RuntimeError("instrumentation does not replace another custom factory")
        kwargs["factory"] = ObservedConnection
        connection = original(*args, **kwargs)
        observer.emit("connection_opened", settings=connection_settings(connection),
                      compile_options=[row[0] for row in connection.execute("PRAGMA compile_options")])
        return connection

    sqlite3.connect = connect
    return original


def minimal_writer(db, fixture, observer):
    connection = sqlite3.connect(db, isolation_level=None, timeout=30)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA temp_store=FILE")
        connection.execute("BEGIN IMMEDIATE")
        observer.emit("hook_after_begin", settings=connection_settings(connection))
        def rows():
            # Fixture26's independently published insertion recipe. There is
            # no CSV parser, validation, or SDK receipt computation here.
            new_count = 2 * fixture["n"] // 5
            for index in range(new_count):
                yield (f"n{index:09d}", str((17 * (index + new_count) + 11) % 1000001))
        connection.executemany("INSERT OR IGNORE INTO items(id,value) VALUES(?,?)", rows())
        observer.emit("hook_after_effect")
        version = "qkf.run26.control.v1"
        fingerprint = _hash(version + "\x00" + fixture["payload_sha"])
        receipt = {"schema": version, "format_version": version,
                   "operation_key": "run26", "payload_sha256": fixture["payload_sha"],
                   "payload_fingerprint": fingerprint,
                   "canonical_input_sha256": fixture["canonical_input_sha"],
                   "before_sha256": fixture["before_sha"],
                   "after_sha256": fixture["after_sha"],
                   "counts": fixture["counts"], "goal_verified": True}
        encoded = canonical(receipt)
        connection.execute("INSERT INTO qkf_import_receipts VALUES(?,?,?,?,?,?)",
                           ("run26", version, fixture["payload_sha"], fingerprint,
                            encoded, _hash(encoded)))
        observer.emit("hook_after_receipt")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--fixture-json", required=True, type=Path)
    parser.add_argument("--engine", required=True,
                        choices=("minimal", "minimal_pressure", "ordinary", "staged", "reference"))
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--kill-at", choices=("none", "before_commit", "after_commit"), default="none")
    arguments = parser.parse_args()
    fixture = json.loads(arguments.fixture_json.read_text(encoding="utf-8"))
    observer = Observer(arguments.trace, arguments.db)
    original_connect = None
    pressure = None
    started = time.monotonic_ns()
    try:
        observer.emit("actor_started", engine=arguments.engine, kill_at=arguments.kill_at,
                      environment=environment(arguments.db), pressure_bytes=0)
        original_connect = install_connection_observer(observer, arguments.kill_at)
        if arguments.engine == "minimal_pressure":
            pressure = bytearray(PRESSURE_BYTES)
            for offset in range(0, PRESSURE_BYTES, 4096):
                pressure[offset] = 1
            observer.emit("pressure_allocated", allocated_bytes=len(pressure),
                          peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if arguments.engine.startswith("minimal"):
            receipt = minimal_writer(arguments.db, fixture, observer)
        else:
            sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))
            def hook(point):
                observer.emit("hook_" + point)
            if arguments.engine == "reference":
                from external_reference import ClassicImporter
                importer = ClassicImporter(arguments.db)
            else:
                from qkf_import import SafeImporter
                importer = SafeImporter(arguments.db, engine=arguments.engine)
            receipt = importer.import_csv(arguments.csv, "run26", fault=hook)
        observer.emit("actor_returned", method_ns=time.monotonic_ns() - started,
                      peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                      allocated_bytes=len(pressure) if pressure is not None else 0)
        print(canonical({"status": "ok", "receipt": receipt,
                         "method_ns": time.monotonic_ns() - started,
                         "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                         "allocated_bytes": len(pressure) if pressure is not None else 0}), flush=True)
        return 0
    except BaseException as error:
        observer.emit("actor_exception", error_type=type(error).__name__, error=str(error))
        print(canonical({"status": "error", "error_type": type(error).__name__, "error": str(error)}), flush=True)
        traceback.print_exc()
        return 1
    finally:
        if original_connect is not None:
            sqlite3.connect = original_connect
        observer.close()


if __name__ == "__main__":
    raise SystemExit(main())
