"""Dependency adaptations for the upstream PyParse v1 child process."""
import runpy
import sys
from pathlib import Path
from unittest.mock import patch


def run_engine(script, args):
    import numpy as np
    import pandas as pd
    from matplotlib.axes import Axes

    read_csv = pd.read_csv
    draw_pie = Axes.pie

    def read_platemap(*positional, **keywords):
        table = read_csv(*positional, **keywords)
        # Upstream fills every missing cell with ''. Preserve numeric values
        # while allowing that sentinel in columns that actually have blanks.
        for name in table.select_dtypes(include='number'):
            if table[name].isna().any():
                table[name] = table[name].astype(object)
        return table

    def draw_nonempty_pie(axis, values, *positional, **keywords):
        if np.asarray(values).ndim == 1 and np.all(np.asarray(values) == 0):
            return ([], []) if keywords.get('autopct') is None else ([], [], [])
        return draw_pie(axis, values, *positional, **keywords)

    script = Path(script).resolve()
    with patch.object(pd, 'read_csv', read_platemap), patch.object(Axes, 'pie', draw_nonempty_pie), patch.object(sys, 'argv', [str(script), *args]), patch.object(sys, 'path', [str(script.parent), *sys.path]):
        runpy.run_path(str(script), run_name='__main__')
    return 0


if __name__ == '__main__':
    raise SystemExit(run_engine(sys.argv[1], sys.argv[2:]))
