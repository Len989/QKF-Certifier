"""Tests of the experiment harness, not additional external algorithm coverage."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.external.frozen_v1 import experiment as e


class ExperimentTests(unittest.TestCase):
    def test_engine_frozen(self):
        self.assertEqual(len(e.check_engine()), 79)

    def test_engine_changes_rejected(self):
        with patch.object(e, "sha", return_value="wrong"):
            with self.assertRaisesRegex(ValueError, "frozen engine bytes"):
                e.check_engine()

    def test_corpus_population(self):
        c = e.load(e.HERE / "CORPUS.json")
        self.assertEqual(len(c["population"]), 12)
        self.assertEqual(len({x["id"] for x in c["population"]}), 12)
        self.assertEqual(len({c["sources"][x["source"]]["repository"] for x in c["population"]}), 2)
        self.assertFalse(c["rules"]["native_is_proof"])

    def test_byte_preserving_extract(self):
        s = "class A { /* ignored } */ public static long f(long i) { return i; } }"
        body, spans = e.extract_method(s, "f", "long i")
        self.assertEqual(body, "public static long f(long i) { return i; }")
        self.assertEqual(s[spans["start_character"]:spans["end_character"]], body)

    def test_ignores_comment_fake_declaration(self):
        s = "// public static long f(long i) {wrong}\npublic static long f(long i) {return i;}"
        self.assertEqual(e.extract_method(s, "f", "long i")[0], "public static long f(long i) {return i;}")

    def test_string_braces(self):
        s = 'public static long f(long i) { String x = "} {"; return i; }'
        self.assertEqual(e.extract_method(s, "f", "long i")[0], s)

    def test_overload_selection(self):
        s = "public static long f(int i) {return 0;} public static long f(long i) {return i;}"
        self.assertEqual(e.extract_method(s, "f", "long i")[0], "public static long f(long i) {return i;}")

    def test_duplicate_refused(self):
        s = "public static long f(long i) {return i;}"
        with self.assertRaisesRegex(ValueError, "exactly one"):
            e.extract_method(s + s, "f", "long i")

    def test_missing_not_substituted(self):
        s = "public static long different(long i) {return i;}"
        with self.assertRaisesRegex(ValueError, "exactly one"):
            e.extract_method(s, "wanted", "long i")

    def test_unclosed_refused(self):
        with self.assertRaisesRegex(ValueError, "closed selected"):
            e.extract_method("public static long f(long i) {", "f", "long i")

    def test_blob_tamper_refused(self):
        identity = {"blob": "0" * 40, "path": "test.java"}
        with self.assertRaisesRegex(ValueError, "Git blob differs"):
            e.check_blob(b"not the original", identity)

    def test_blob_success(self):
        import hashlib
        raw = b"sample\n"
        identity = {"path": "test.java", "blob": hashlib.sha1(b"blob 7\0" + raw).hexdigest()}
        self.assertTrue(e.check_blob(raw, identity)["git_blob_verified"])

    def test_unsupported_is_not_counterexample(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "method.java"
            p.write_text("public static long lowestOneBit(long i) { return i & -i; }")
            for profile in ("ascending", "descending"):
                out = e.probe(profile, p, 10)["outcome"]
                self.assertEqual(out["status"], "source_unsupported")
                self.assertFalse(out["is_proof"])

    def test_timeout_not_unsupported(self):
        fake = {"timeout": True, "returncode": None, "stdout": "", "stderr": "", "seconds": 1}
        with patch.object(e, "child", return_value=fake):
            self.assertEqual(e.probe("ascending", Path("x"), 1)["outcome"]["status"], "timeout")

    def test_process_error_not_unsupported(self):
        fake = {"timeout": False, "returncode": 1, "stdout": "", "stderr": "error", "seconds": 1}
        with patch.object(e, "child", return_value=fake):
            self.assertEqual(e.probe("ascending", Path("x"), 1)["outcome"]["status"], "process_error")

    def test_actual_timeout(self):
        import sys
        r = e.child([sys.executable, "-c", "import time; time.sleep(2)"], 0.05)
        self.assertTrue(r["timeout"])

    def test_save_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "data.json"
            e.save(p, {"original": True})
            with self.assertRaises(FileExistsError):
                e.save(p, {"original": False})
            self.assertEqual(json.loads(p.read_text()), {"original": True})

    def test_word_population_deterministic(self):
        c = e.load(e.HERE / "CORPUS.json")["native"]
        self.assertEqual(e.words(c), e.words(c))
        self.assertEqual(len(e.words(c)), len(set(e.words(c))))
        self.assertIn(1 << 63, e.words(c))
        self.assertIn(e.MASK, e.words(c))

    def test_power_domain(self):
        c = e.load(e.HERE / "CORPUS.json")
        case = next(x for x in c["population"] if x["method"] == "nextHighestPowerOfTwo")
        self.assertTrue(all(0 <= x[0] <= 1 << 62 for x in e.inputs(case, c["native"])))
        with self.assertRaises(ValueError):
            e.oracle(case["method"], [1 << 63])

    def test_bit_queries_zero_extremes(self):
        self.assertEqual(e.oracle("highestOneBit", [0]), 0)
        self.assertEqual(e.oracle("lowestOneBit", [0]), 0)
        self.assertEqual(e.oracle("numberOfLeadingZeros", [0]), 64)
        self.assertEqual(e.oracle("numberOfTrailingZeros", [0]), 64)
        self.assertEqual(e.oracle("bitCount", [e.MASK]), 64)
        self.assertEqual(e.oracle("reverseBytes", [0x0102030405060708]), 0x0807060504030201)

    def test_zigzag_oracle_roundtrip(self):
        for signed in list(range(-100, 100)) + [-(1 << 63), (1 << 63) - 1]:
            encoded = e.oracle("zigZagEncode", [signed & e.MASK])
            decoded = e.oracle("zigZagDecode", [encoded])
            self.assertEqual(e.signed(decoded), signed)

    def test_interleave_oracle_laws(self):
        for a in (0, 1, 65535, (1 << 32) - 1):
            for b in (0, 1, 65535, 1 << 31):
                z = e.oracle("interleave", [a, b])
                self.assertEqual(e.oracle("deinterleave", [z]), a)
                self.assertEqual(e.oracle("deinterleave", [z >> 1]), b)
                self.assertEqual(e.oracle("flipFlop", [z]), e.oracle("interleave", [b, a]))


if __name__ == "__main__":
    unittest.main()
