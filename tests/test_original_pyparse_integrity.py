from __future__ import annotations

import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_PYPARSE_SHA256 = "BCC3C1608CC902DC487605579CF8BE0BFA1B428FB135F5C168F0BCE1AB142012"


class OriginalPyParseIntegrityTests(unittest.TestCase):
    def test_original_pyparse_source_is_unchanged(self):
        source = ROOT / "PyParse" / "PyParse.py"
        digest = hashlib.sha256(source.read_bytes()).hexdigest().upper()
        self.assertEqual(ORIGINAL_PYPARSE_SHA256, digest)


if __name__ == "__main__":
    unittest.main()
