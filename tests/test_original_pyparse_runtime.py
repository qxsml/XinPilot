"""Regression coverage for dependency behavior in the original-engine child."""
import tempfile
import unittest
from pathlib import Path

from xinpilot.application.original_pyparse_runtime import run_engine


class OriginalRuntimeTest(unittest.TestCase):
    def test_blank_cells_and_zero_pie(self):
        import pandas as pd
        from matplotlib.axes import Axes
        previous_reader, previous_pie = pd.read_csv, Axes.pie
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / 'check.py'
            script.write_text("""from io import StringIO
import pandas as pd
from matplotlib.figure import Figure
table = pd.read_csv(StringIO('well,amount\\nA1,2.5\\nA2,\\n'))
table.fillna('', inplace=True)
assert list(table.amount) == [2.5, '']
axis = Figure().subplots()
axis.pie([])
axis.pie([0, 0])
assert not axis.patches
axis.pie([1, 3])
assert len(axis.patches) == 2
""", encoding='utf-8')
            self.assertEqual(run_engine(script, []), 0)
        self.assertIs(pd.read_csv, previous_reader)
        self.assertIs(Axes.pie, previous_pie)
