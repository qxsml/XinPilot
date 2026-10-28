from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from cheminformatics_frame import CheminformaticsFrame  # noqa: E402


class ProductResultsExportTests(unittest.TestCase):
    def setUp(self):
        self.frame = object.__new__(CheminformaticsFrame)
        self.frame.product_structure_uv_source_by_key = {
            "lcms:A1": "pyparse",
            "lcms:A2": "manual",
        }
        self.frame.pyparse_purity_by_well = {"A1": "81.25%", "A2": "72.00%", "A3": "66.00%"}
        self.frame.modified_pyparse_purity_by_product = {
            "CCC": {"A3": "55.50%"},
        }
        self.frame.product_structure_manual_notes = {
            "lcms:A2": {"manual_purity": "93.4%", "comments": "reviewed"},
        }
        self.rows = [
            {
                "reaction_name": "RXN-001",
                "reaction_well": "B1",
                "pyparse_well": "A1",
                "desired product exact mass": "46.0419",
                "desired product mw": "46.069",
                "desired product formula": "C2H6O",
                "desired product smiles": "CCO",
            },
            {
                "reaction_name": "RXN-002",
                "reaction_well": "B2",
                "pyparse_well": "A2",
                "desired product exact mass": "45.0578",
                "desired product mw": "45.085",
                "desired product formula": "C2H7N",
                "desired product smiles": "CCN",
            },
            {
                "reaction_name": "RXN-003",
                "reaction_well": "B3",
                "pyparse_well": "A3",
                "desired product exact mass": "44.0626",
                "desired product mw": "44.097",
                "desired product formula": "C3H8",
                "desired product smiles": "CCC",
            },
        ]
        self.frame._pyparse_rows = lambda: list(self.rows)

    def test_export_rows_use_each_products_selected_heatmap_purity(self):
        exported = self.frame._product_results_export_rows()

        self.assertEqual(
            ["81.25%", "93.4%", "55.50%"],
            [row["UV254 Purity"] for row in exported],
        )
        self.assertEqual(
            ["PyParse", "Manual", "Modified PyParse"],
            [row["UV254 Purity Source"] for row in exported],
        )
        self.assertEqual("RXN-001", exported[0]["Reaction Number"])
        self.assertEqual("46.069", exported[0]["Molecular Weight"])
        self.assertEqual("C2H6O", exported[0]["Molecular Formula"])

    def test_export_writes_requested_headers_in_order(self):
        self.frame._save_current_product_structure_manual_fields = lambda: None
        self.frame.logw = lambda *_args, **_kwargs: None
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "product-results.csv"
            with (
                patch("cheminformatics_frame.filedialog.asksaveasfilename", return_value=str(output)),
                patch("cheminformatics_frame.messagebox.showinfo"),
            ):
                self.frame._export_product_results_csv()

            with output.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(
            [
                "Reaction Number",
                "Reaction Well",
                "LCMS Well",
                "Exact Mass",
                "Molecular Weight",
                "Molecular Formula",
                "Product SMILES",
                "UV254 Purity",
                "UV254 Purity Source",
            ],
            list(rows[0]),
        )
        self.assertEqual(3, len(rows))
        self.assertEqual("55.50%", rows[2]["UV254 Purity"])

    def test_export_warns_when_no_product_rows_exist(self):
        self.frame._save_current_product_structure_manual_fields = lambda: None
        self.frame._pyparse_rows = lambda: [{"reaction_name": "RXN-blank", "desired product smiles": ""}]

        with (
            patch("cheminformatics_frame.messagebox.showwarning") as warning,
            patch("cheminformatics_frame.filedialog.asksaveasfilename") as save_dialog,
        ):
            self.frame._export_product_results_csv()

        warning.assert_called_once()
        save_dialog.assert_not_called()


if __name__ == "__main__":
    unittest.main()
