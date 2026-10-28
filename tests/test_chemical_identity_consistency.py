"""Chemical identity and imported sample mapping must own their analytical results."""
import copy
import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from cheminformatics_frame import CheminformaticsFrame
from integrated_full_software import IntegratedFullApp
import impurity_analysis


class ChemicalIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.records = []
        cls.frame = CheminformaticsFrame(cls.root, lambda: [SimpleNamespace(values=record) for record in cls.records], lambda: [])

    @classmethod
    def tearDownClass(cls):
        for token in cls.root.tk.call("after", "info"):
            cls.root.tk.call("after", "cancel", token)
        cls.root.destroy()

    def setUp(self):
        self.f = self.frame
        self.f.clear_for_next_synthesis_step()
        self.records[:] = [
            {"ID": "ARYL", "SMILES": "Clc1ccccc1"},
            {"ID": "BORON", "SMILES": "OB(O)c1ccccc1"},
            {"ID": "OTHER", "SMILES": "OB(O)c1ccccc1"},
        ]
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "products.csv"
        self.info = patch("cheminformatics_frame.messagebox.showinfo").start()
        self.addCleanup(patch.stopall)

    def prepare(self, custom=False):
        rows = [{"source": "External Import", "chemical": cid, "chemical_id": cid,
                 "well": well, "volume_uL": 10, "dest_mode": "96-well horizontal",
                 "is_building_block": True}
                for well, ids in (("A1", ("ARYL", "BORON")), ("A2", ("ARYL", "OTHER")))
                for cid in ids]
        self.f.push_from_external(rows)
        self.f.pyparse_wells = {"A1": "C1", "A2": "C2"}
        if custom:
            self.f.custom_template_text.insert("1.0", "[c:1]Cl.[c:2]B(O)O>>[c:1][c:2]")
            self.f._generate_custom_products(False)
        else:
            reaction = next(r for r in self.f.reactions if r["id"] == "suzuki")
            self.f.reaction_var.set(reaction["label"])
            self.f._generate()
        products = self.f._pyparse_rows()
        self.product = products[0]["desired product smiles"]
        self.assertTrue(self.product)
        self.f.lcms_target_smiles_by_well = {"A1": self.product, "A2": self.product}
        self.f.modified_pyparse_purity_by_product = {self.product: {"C1": "83%", "C2": "92%"}}
        self.f.pyparse_purity_by_well = {"C1": "81%", "C2": "90%"}
        self.f.product_structure_manual_notes = {"lcms:C1": {"manual_purity": "77", "comments": "sample note"}}
        return rows, products

    def import_csv(self, contents, confirm=True):
        self.path.write_text("Reaction well,LCMS well,Product SMILES\n" + contents)
        with patch("cheminformatics_frame.filedialog.askopenfilename", return_value=str(self.path)), \
             patch("cheminformatics_frame.messagebox.askyesno", return_value=confirm) as ask:
            self.f._input_product_details()
        return ask

    def test_standard_smiles_edit_detaches_old_target_before_read_and_next_step(self):
        _, previous = self.prepare()
        self.records[1]["SMILES"] = "Cc1ccc(B(O)O)cc1"
        # A getter invoked with an earlier selected row must synchronize too.
        self.assertEqual("", self.f._modified_pyparse_purity_for_row(previous[0]))
        rows = self.f._pyparse_rows()
        self.assertNotEqual(self.product, rows[0]["desired product smiles"])
        self.assertNotIn("A1", self.f.lcms_target_smiles_by_well)
        self.assertEqual("92%", self.f._modified_pyparse_purity_for_row(rows[1]))
        self.assertEqual(self.product, self.f.lcms_target_smiles_by_well["A2"])
        self.assertEqual({"comments": "sample note"}, self.f.product_structure_manual_notes["lcms:C1"])
        candidates = IntegratedFullApp._next_step_product_candidates(SimpleNamespace(cheminformatics_tab=self.f))
        self.assertEqual("", candidates[0]["purity"])
        self.assertEqual("92%", candidates[1]["purity"])

    def test_custom_edit_without_repush_removes_automatic_product_and_survives_roundtrip(self):
        rows, _ = self.prepare(custom=True)
        self.records[1]["SMILES"] = "Cc1ccc(B(O)O)cc1"
        state = json.loads(json.dumps(self.f.export_state()))
        self.assertNotIn("A1", state["custom_products"])
        self.assertIn("A2", state["custom_products"])
        self.f.import_state(state)
        self.f.push_from_external(rows)
        current = self.f._pyparse_rows()
        self.assertEqual("", current[0]["desired product smiles"])
        self.assertEqual("", self.f._modified_pyparse_purity_for_row(current[0]))
        self.assertEqual("92%", self.f._modified_pyparse_purity_for_row(current[1]))

    def test_equivalent_smiles_and_unchanged_push_preserve_results(self):
        rows, _ = self.prepare(custom=True)
        self.records[1]["SMILES"] = "B(O)(O)c1ccccc1"
        self.f.push_from_external(rows)
        self.assertEqual(self.product, self.f.custom_products["A1"]["smiles"])
        self.assertEqual("83%", self.f._modified_pyparse_purity_for_row(self.f._pyparse_rows()[0]))

    def test_manual_product_is_preserved_and_review_flag_roundtrips(self):
        self.prepare(custom=True)
        self.f.imported_product_details["A1"] = {"desired product smiles": "CCO"}
        self.f._pyparse_rows()
        self.records[1]["SMILES"] = "Cc1ccc(B(O)O)cc1"
        row = self.f._pyparse_rows()[0]
        self.assertEqual("CCO", row["desired product smiles"])
        self.assertIn("Review Product Details", row["status"])
        self.f._store_reaction_name("A1", "Renamed reaction")
        self.assertIn("A1", self.f.product_review_wells)
        state = json.loads(json.dumps(self.f.export_state()))
        self.f.import_state(state)
        self.assertIn("A1", self.f.product_review_wells)

    def test_intentionally_retained_results_ignore_new_compound_edits(self):
        self.prepare(custom=True)
        with patch.object(self.f, "_ask_clear_pushed", return_value="inputs"):
            self.f._clear_pushed_rows()
        before = self.f._pyparse_rows()
        self.records[1]["SMILES"] = "Cc1ccc(B(O)O)cc1"
        self.assertEqual(before, self.f._pyparse_rows())
        self.assertEqual("83%", self.f._modified_pyparse_purity_for_row(before[0]))

    def test_legacy_project_initializes_baseline_then_detects_edits(self):
        self.prepare(custom=True)
        state = json.loads(json.dumps(self.f.export_state()))
        state.pop("building_block_identity_by_well")
        state.pop("product_review_wells")
        self.f.import_state(state)
        self.assertEqual("83%", self.f._modified_pyparse_purity_for_row(self.f._pyparse_rows()[0]))
        self.records[1]["SMILES"] = "Cc1ccc(B(O)O)cc1"
        self.assertEqual("", self.f._pyparse_rows()[0]["desired product smiles"])

    def test_changed_csv_product_clears_purity_but_keeps_notes_and_other_well(self):
        self.import_csv("A1,C1,CCO\nA2,C2,CCO\n")
        self.f.pyparse_purity_by_well = {"C1": "81%", "C2": "90%"}
        self.f.modified_pyparse_purity_by_product = {"CCO": {"C1": "83%", "C2": "92%"}}
        self.f.product_structure_manual_notes = {"lcms:C1": {"manual_purity": "77", "comments": "keep"}}
        self.import_csv("A1,C1,CCN\nA2,C2,CCO\n")
        row, other = self.f._pyparse_rows()
        for source in ("pyparse", "modified", "manual"):
            self.assertEqual("", self.f._product_structure_purity_for_row(row, source))
        self.assertEqual("92%", self.f._modified_pyparse_purity_for_row(other))
        self.assertEqual({"comments": "keep"}, self.f.product_structure_manual_notes["lcms:C1"])
        self.import_csv("A1,C1,CCO\nA2,C2,CCO\n")
        self.assertEqual("", self.f._modified_pyparse_purity_for_row(self.f._pyparse_rows()[0]))

    def test_identical_csv_preserves_targets_and_existing_assignments(self):
        self.import_csv("A1,C1,CCO\n")
        self.f.modified_pyparse_purity_by_product = {"CCO": {"C1": "83%"}}
        self.f.lcms_target_smiles_by_well = {"A1": "CCO"}
        self.f.product_structure_manual_notes = {"lcms:C1": {"manual_purity": "77", "comments": "keep"}}
        ask = self.import_csv("A1,C1,OCC\n")
        ask.assert_not_called()
        self.assertEqual("83%", self.f._modified_pyparse_purity_for_row(self.f._pyparse_rows()[0]))
        self.assertEqual("77", self.f.product_structure_manual_notes["lcms:C1"]["manual_purity"])
        self.assertEqual({"A1": "CCO"}, self.f.lcms_target_smiles_by_well)

    def test_new_csv_mapping_prompts_then_uses_only_destination_product_result(self):
        self.import_csv("A1,C1,CCO\n")
        self.f.pyparse_wells["A1"] = "C2"
        self.f.modified_pyparse_purity_by_product = {"CCO": {"C2": "91%", "D1": "2%"}}
        self.f.pyparse_purity_by_well = {"C2": "90%", "D1": "60%"}
        self.f.product_structure_manual_notes = {"lcms:C2": {"manual_purity": "99", "comments": "old sample"}}
        before = copy.deepcopy(self.f.export_state())
        ask = self.import_csv("A1,D1,CCO\n", confirm=False)
        ask.assert_called_once()
        self.assertEqual(before, self.f.export_state())
        ask = self.import_csv("A1,D1,CCO\n")
        ask.assert_called_once()
        row = self.f._pyparse_rows()[0]
        self.assertEqual("D1", row["pyparse_well"])
        self.assertEqual("2%", self.f._modified_pyparse_purity_for_row(row))
        self.assertEqual("", self.f._product_structure_purity_for_row(row, "pyparse"))
        self.assertEqual("", self.f._product_structure_purity_for_row(row, "manual"))
        self.assertEqual({"comments": "old sample"}, self.f.product_structure_manual_notes["lcms:C2"])


class AlkyneImpurityIdentityTests(unittest.TestCase):
    def test_homocoupling_preserves_both_substituents_and_all_carbons(self):
        cases = [("CC#C", "CC#CC#CC", "C6H6"),
                 ("CCC#C", "CCC#CC#CCC", "C8H10"),
                 ("C#Cc1ccccc1", "c1ccccc1C#CC#Cc1ccccc1", "C16H10")]
        for reactant, expected, formula in cases:
            with self.subTest(reactant=reactant):
                candidates = impurity_analysis.predict_impurities("sonogashira", "", reactant, "Ic1ccccc1")
                homocoupling = next(row for row in candidates if row["rule_id"] == "terminal_alkyne_homocoupling")
                self.assertEqual(Chem.MolToSmiles(Chem.MolFromSmiles(expected)), homocoupling["smiles"])
                self.assertEqual(formula, homocoupling["formula"])


class ChemicalIdentityReadOnlyTests(unittest.TestCase):
    def test_fresh_legacy_and_cleared_views_do_not_dirty_saved_project(self):
        app = IntegratedFullApp()
        app.withdraw()
        try:
            frame = app.cheminformatics_tab
            for context in ("fresh", "legacy", "cleared"):
                with self.subTest(context=context):
                    if context == "legacy":
                        data = app._project_payload()
                        data["cheminformatics"].pop("building_block_identity_by_well", None)
                        data["cheminformatics"].pop("product_review_wells", None)
                        app._apply_project_data(data)
                    elif context == "cleared":
                        frame.clear_for_next_synthesis_step()
                    self.assertEqual({}, frame.building_block_identity_by_well)
                    app._mark_project_saved()
                    self.assertFalse(app._check_project_changes())
                    frame._pyparse_rows()
                    frame._refresh_product_details_preview()
                    frame._refresh_pyparse_preview()
                    self.assertFalse(app._check_project_changes())
        finally:
            for token in app.tk.call("after", "info"):
                app.tk.call("after", "cancel", token)
            app.destroy()


if __name__ == "__main__":
    unittest.main()
