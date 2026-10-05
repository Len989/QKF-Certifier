"""Adversarial cold-audit checks with independent tiny fixtures."""

import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from audit26 import audit_pair
from fixture26 import after_rows, prepare


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Audit26Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fixture = prepare(self.root / "fixture", 100)
        self.pair = self.root / "pair"
        self.pair.mkdir()
        self.database = self.pair / "database.sqlite"
        shutil.copyfile(self.fixture["db"], self.database)
        self.spec = {"backend": "minimal", "operation_key": "run26"}

    def tearDown(self):
        self.temp.cleanup()

    def receipt(self, sdk=False):
        version = "qkf.import.csv.v1" if sdk else "qkf.run26.control.v1"
        fingerprint = hashlib.sha256((version + "\0" + self.fixture["payload_sha"]).encode()).hexdigest()
        return {
            "schema": "qkf.import.receipt.v1" if sdk else "qkf.run26.control.v1",
            "format_version": version, "operation_key": "run26",
            "payload_sha256": self.fixture["payload_sha"], "payload_fingerprint": fingerprint,
            "canonical_input_sha256": self.fixture["canonical_input_sha"],
            "before_sha256": self.fixture["before_sha"], "after_sha256": self.fixture["after_sha"],
            "counts": self.fixture["counts"], "goal_verified": True,
        }

    def put_receipt(self, connection, receipt=None):
        receipt = receipt or self.receipt()
        text = encoded(receipt)
        connection.execute("INSERT INTO qkf_import_receipts VALUES(?,?,?,?,?,?)", (
            receipt["operation_key"], receipt["format_version"], receipt["payload_sha256"],
            receipt["payload_fingerprint"], text, hashlib.sha256(text.encode()).hexdigest()))

    def make_post(self, receipt=None):
        connection = sqlite3.connect(self.database)
        try:
            connection.execute("DELETE FROM items")
            connection.executemany("INSERT INTO items VALUES(?,?)", after_rows(100))
            self.put_receipt(connection, receipt)
            connection.commit()
        finally:
            connection.close()

    def audit(self):
        result = audit_pair(self.pair, self.spec, self.fixture)
        self.assertTrue(result["original_unchanged"], result)
        return result

    def test_pre_is_valid_and_does_not_change_original(self):
        result = self.audit()
        self.assertTrue(result["pass"], result)
        self.assertEqual(result["state"], "PRE")
        self.assertEqual(result["receipt"]["count"], 0)

    def test_control_post_and_sdk_post_valid(self):
        self.make_post()
        self.assertEqual(self.audit()["state"], "POST")
        self.spec["backend"] = "minimal_pressure"
        self.assertEqual(self.audit()["state"], "POST")
        connection = sqlite3.connect(self.database)
        try:
            connection.execute("DELETE FROM qkf_import_receipts")
            self.put_receipt(connection, self.receipt(sdk=True))
            connection.commit()
        finally:
            connection.close()
        self.spec["backend"] = "ordinary"
        self.assertTrue(self.audit()["pass"])

    def test_pre_items_with_valid_post_receipt_is_mixed(self):
        connection = sqlite3.connect(self.database)
        try:
            self.put_receipt(connection)
            connection.commit()
        finally:
            connection.close()
        result = self.audit()
        self.assertFalse(result["pass"], result)
        self.assertEqual(result["state"], "MIXED")
        self.assertEqual(result["items"]["state"], "PRE")
        self.assertTrue(result["receipt"]["valid"])

    def test_changed_old_value_and_missing_new_row_fail(self):
        self.make_post()
        connection = sqlite3.connect(self.database)
        try:
            connection.execute("UPDATE items SET value='replacement' WHERE id='b000000000'")
            connection.execute("DELETE FROM items WHERE id='n000000039'")
            connection.commit()
        finally:
            connection.close()
        result = self.audit()
        self.assertFalse(result["pass"], result)
        self.assertEqual(result["items"]["state"], "MIXED")

    def test_receipt_count_forgery_with_recomputed_checksum_fails(self):
        forged = self.receipt()
        forged["counts"] = dict(forged["counts"], input_rows=101)
        self.make_post(forged)
        result = self.audit()
        self.assertFalse(result["pass"], result)
        self.assertFalse(result["receipt"]["valid"])

    def test_boolean_count_not_accepted_as_integer(self):
        # Python dict equality can treat True as 1; exact count types are required.
        self.fixture = prepare(self.root / "small", 10)
        shutil.copyfile(self.fixture["db"], self.database)
        forged = self.receipt()
        forged["counts"] = dict(forged["counts"], invalid_rows=True)
        connection = sqlite3.connect(self.database)
        try:
            connection.execute("DELETE FROM items")
            connection.executemany("INSERT INTO items VALUES(?,?)", after_rows(10))
            self.put_receipt(connection, forged)
            connection.commit()
        finally:
            connection.close()
        self.assertFalse(self.audit()["pass"])

    def test_checksum_mismatch_fails(self):
        self.make_post()
        connection = sqlite3.connect(self.database)
        try:
            connection.execute("UPDATE qkf_import_receipts SET receipt_sha256=?", ("0" * 64,))
            connection.commit()
        finally:
            connection.close()
        self.assertFalse(self.audit()["pass"])

    def test_uncommitted_spill_recovers_only_copy(self):
        program = """import os, sqlite3, sys
c=sqlite3.connect(sys.argv[1])
c.execute('PRAGMA journal_mode=DELETE')
c.execute('PRAGMA synchronous=FULL')
c.execute('PRAGMA cache_size=1')
c.execute('BEGIN IMMEDIATE')
c.execute('UPDATE items SET value=?', ('X'*4096,))
os._exit(19)
"""
        process = subprocess.run([sys.executable, "-c", program, str(self.database)], capture_output=True)
        self.assertEqual(process.returncode, 19, process.stderr)
        self.assertTrue(self.database.with_name("database.sqlite-journal").exists())
        result = self.audit()
        self.assertEqual(result["state"], "PRE", result)
        self.assertTrue(result["pass"], result)
        self.assertTrue(result["journal_present"])

    def test_fixture_hash_metadata_forgery_fails(self):
        self.fixture["after_sha"] = "0" * 64
        result = audit_pair(self.pair, self.spec, self.fixture)
        self.assertFalse(result["pass"])
        self.assertIn("independent oracle", result["error"])


if __name__ == "__main__":
    unittest.main()
