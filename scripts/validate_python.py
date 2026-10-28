"""Run regression checks with temporary files confined to this edition."""
from pathlib import Path
import sys
import tempfile
import unittest


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    temp_root = root / 'artifacts' / 'python-tests' / 'temp'
    temp_root.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(temp_root)
    suite = unittest.defaultTestLoader.discover(str(root / 'tests'))
    with (root / 'artifacts' / 'python-tests' / 'validation.txt').open('w', encoding='utf-8') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    print(f'{result.testsRun} tests; {len(result.failures)} failures; {len(result.errors)} errors; {len(result.skipped)} skipped')
    sys.exit(not result.wasSuccessful())
