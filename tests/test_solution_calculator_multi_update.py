import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "toolkit" / "solution_calculator"))
from solution_calculator import SolutionCalculatorApp

class MultiRowUpdateTests(unittest.TestCase):
    def setUp(self):
        self.app = SolutionCalculatorApp({"products": [
            {"product_id": "P1", "product_name": "One", "product_smiles": "CCO", "product_mw": "100"},
            {"product_id": "P2", "product_name": "Two", "product_smiles": "CCN", "product_mw": "200"},
            {"product_id": "P3", "product_name": "Three", "product_smiles": "CCC", "product_mw": "300"}]})
        self.app.withdraw()
        for i, row in enumerate(self.app.batch_rows):
            row.update(amount=str(i+1), amount_unit="mg", mass_purity="100", target_mm="10", solvent="DMSO", rounding_ul="0")
        self.app.import_batch_rows = copy.deepcopy(self.app.batch_rows)
        self.app._refresh_batch_tree()
        self.app._refresh_import_tree()
        self.app.update()

    def tearDown(self):
        self.app.update_idletasks()
        self.app.destroy()

    def select(self, prefix, *ids):
        getattr(self.app, prefix+"_tree").selection_set(*ids)
        self.app.update()
        getattr(self.app, "_load_selected_"+prefix+"_row")()

    def test_multiple_rows_change_only_target_and_recalculate_individually(self):
        for prefix in ("batch", "import"):
            with self.subTest(prefix=prefix):
                rows = self.app.batch_rows if prefix=="batch" else self.app.import_batch_rows
                untouched=copy.deepcopy(rows[2])
                self.select(prefix,"0","1")
                self.assertEqual("",getattr(self.app,prefix+"_amount_var").get())
                getattr(self.app,prefix+"_target_var").set("20")
                self.app.update()
                self.assertTrue(getattr(self.app,"_save_selected_"+prefix+"_row")())
                self.app.update()
                self.assertEqual(["1","2"],[r["amount"] for r in rows[:2]])
                self.assertEqual(["20","20"],[r["target_mm"] for r in rows[:2]])
                self.assertEqual(untouched,rows[2])
                self.assertEqual({"0","1"},set(getattr(self.app,prefix+"_tree").selection()))
                self.assertTrue(all(r["final_volume_ul"] for r in rows[:2]))
                self.assertEqual(["P1","P2"],[r["product_id"] for r in rows[:2]])

    def test_explicit_blank_single_selection_and_stale_edit_reset(self):
        for prefix in ("batch","import"):
            rows=self.app.batch_rows if prefix=="batch" else self.app.import_batch_rows
            self.select(prefix,"0")
            getattr(self.app,prefix+"_amount_var").set("99")
            self.select(prefix,"0","1")
            getattr(self.app,prefix+"_solvent_var").set("")
            getattr(self.app,"_save_selected_"+prefix+"_row")()
            self.assertEqual(["1","2"],[r["amount"] for r in rows[:2]])
            self.assertEqual(["", ""],[r["solvent"] for r in rows[:2]])
            self.select(prefix,"1")
            getattr(self.app,prefix+"_amount_var").set("4")
            getattr(self.app,"_save_selected_"+prefix+"_row")()
            self.assertEqual("4",rows[1]["amount"])
            self.assertEqual("1",rows[0]["amount"])

    @patch("solution_calculator.messagebox.showwarning")
    def test_empty_selection_and_unchanged_selection_are_noops(self, warning):
        self.select("batch")
        before=copy.deepcopy(self.app.batch_rows)
        self.assertFalse(self.app._save_selected_batch_row())
        warning.assert_called_once()
        self.select("batch","0","1")
        self.assertTrue(self.app._save_selected_batch_row())
        self.assertEqual(before,self.app.batch_rows)

if __name__=="__main__":unittest.main()
