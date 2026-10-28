from __future__ import annotations

import sys
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from cheminformatics_frame import CheminformaticsFrame  # noqa: E402


class _FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _FakeNotebook:
    def __init__(self, title):
        self.title = title

    def tab(self, _which, _option):
        return self.title


class _FakeTree:
    def __init__(self, rows, selected=()):
        self.rows = {str(iid): tuple(values) for iid, values in rows}
        self.selected = tuple(str(iid) for iid in selected)

    def get_children(self):
        return tuple(self.rows)

    def selection(self):
        return self.selected

    def item(self, iid, option=None, **kwargs):
        iid = str(iid)
        if "values" in kwargs:
            self.rows[iid] = tuple(kwargs["values"])
        if option == "values":
            return self.rows[iid]
        return {"values": self.rows[iid]}


class ReactionNameEditingTests(unittest.TestCase):
    def setUp(self):
        self.frame = object.__new__(CheminformaticsFrame)
        self.frame.name_start_var = _FakeVar()
        self.frame.reaction_name_edit_well = ""
        self.frame.reaction_names = {"A1": "KEEP-01", "A2": "KEEP-02"}
        self.frame.imported_product_details = {}
        self.frame.product_details_generated = False
        self.frame.inner_nb = _FakeNotebook("Product Details")
        self.frame.preview = _FakeTree([
            ("0", ("KEEP-01", "A1", "R1", "", "", "")),
            ("1", ("KEEP-02", "A2", "R2", "", "", "")),
            ("2", ("OLD-03", "A3", "R3", "", "", "")),
            ("3", ("OLD-04", "A4", "R4", "", "", "")),
        ], selected=("1",))
        self.frame.custom_preview = _FakeTree([
            ("0", ("A1", "KEEP-01", "R1", "", "", "", "")),
            ("1", ("A2", "KEEP-02", "R2", "", "", "", "")),
            ("2", ("A3", "OLD-03", "R3", "", "", "", "")),
            ("3", ("A4", "OLD-04", "R4", "", "", "", "")),
        ])

    def test_selecting_product_row_loads_and_typing_updates_that_row(self):
        self.frame._on_product_details_row_select()
        self.assertEqual("KEEP-02", self.frame.name_start_var.get())
        self.assertEqual("A2", self.frame.reaction_name_edit_well)

        self.frame.name_start_var.set("XQ-RXN-22")
        self.frame._save_reaction_name_edit()

        self.assertEqual("XQ-RXN-22", self.frame.reaction_names["A2"])
        self.assertEqual("XQ-RXN-22", self.frame.preview.item("1", "values")[0])
        self.assertEqual("XQ-RXN-22", self.frame.custom_preview.item("1", "values")[1])

    def test_typing_without_a_selected_row_does_not_modify_a_stale_row(self):
        self.frame.reaction_name_edit_well = "A2"
        self.frame.preview.selected = ()
        self.frame.name_start_var.set("SHOULD-NOT-SAVE")

        self.frame._save_reaction_name_edit()

        self.assertEqual("KEEP-02", self.frame.reaction_names["A2"])

    def test_fill_down_starts_at_selected_product_row_and_keeps_rows_above(self):
        self.frame.preview.selected = ("2",)
        self.frame._on_product_details_row_select()
        self.frame.name_start_var.set("XQ-RXN-03")

        self.frame._fill_reaction_names()

        self.assertEqual("KEEP-01", self.frame.reaction_names["A1"])
        self.assertEqual("KEEP-02", self.frame.reaction_names["A2"])
        self.assertEqual("XQ-RXN-03", self.frame.reaction_names["A3"])
        self.assertEqual("XQ-RXN-04", self.frame.reaction_names["A4"])
        self.assertEqual("XQ-RXN-03", self.frame.preview.item("2", "values")[0])
        self.assertEqual("XQ-RXN-04", self.frame.custom_preview.item("3", "values")[1])

    def test_fill_down_without_selection_still_starts_at_top(self):
        self.frame.preview.selected = ()
        self.frame.name_start_var.set("PLATE-07")

        self.frame._fill_reaction_names()

        self.assertEqual("PLATE-07", self.frame.reaction_names["A1"])
        self.assertEqual("PLATE-08", self.frame.reaction_names["A2"])
        self.assertEqual("PLATE-09", self.frame.reaction_names["A3"])
        self.assertEqual("PLATE-10", self.frame.reaction_names["A4"])


if __name__ == "__main__":
    unittest.main()
