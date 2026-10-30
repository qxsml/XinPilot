from __future__ import annotations

import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_PYPARSE_SHA256 = "F8AE5FFD5E55E1A7DD2EA28C60AEE6A6E1AED9FF07E6282F63B91D1161924FCE"


class OriginalPyParseIntegrityTests(unittest.TestCase):
    def test_original_pyparse_source_is_unchanged(self):
        source = ROOT / "PyParse" / "PyParse.py"
        digest = hashlib.sha256(source.read_bytes()).hexdigest().upper()
        self.assertEqual(ORIGINAL_PYPARSE_SHA256, digest)


if __name__ == "__main__":
    unittest.main()
