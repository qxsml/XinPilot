from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from cheminformatics_frame import CheminformaticsFrame  # noqa: E402


class _EditorOpened(Exception):
    pass


class _FakePreview:
    def selection(self):
        return ("0",)

    def item(self, _iid, _option):
        return ("RXN-1", "A1", "Reactant 1", "Reactant 2", "", "")


class ProductDetailManualEditTests(unittest.TestCase):
    def test_blank_product_smiles_row_still_opens_editor(self):
        frame = object.__new__(CheminformaticsFrame)
        frame.preview = _FakePreview()
        frame._pyparse_rows = lambda: [{
            "reaction_well": "A1",
            "desired product smiles": "",
        }]

        with patch("cheminformatics_frame.tk.Toplevel", side_effect=_EditorOpened):
            with self.assertRaises(_EditorOpened):
                frame._edit_selected_product_detail()


if __name__ == "__main__":
    unittest.main()
