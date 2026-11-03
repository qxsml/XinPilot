"""Protect the original engine against changes from its pinned upstream bytes."""
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class OriginalPyParseIntegrityTests(unittest.TestCase):
    def test_original_engine_matches_pinned_upstream(self):
        manifest = json.loads((ROOT / "PyParse/UPSTREAM_SHA256.json").read_text())
        for name, expected in manifest["files"].items():
            with self.subTest(file=name):
                self.assertEqual(expected, hashlib.sha256((ROOT / "PyParse" / name).read_bytes()).hexdigest())

if __name__ == "__main__":
    unittest.main()
